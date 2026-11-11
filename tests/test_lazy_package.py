"""``import sharpit`` stays cheap: the public names load on first use (ci-speed spec §4.2).

Each import case runs in a fresh interpreter, so what it counts is what ``import sharpit`` itself loads; the pytest
process running this file has imported everything already.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BLOCK_FASTAPI = """
    import sys

    class _NoFastAPI:  # a missing [fastapi] extra: the import fails as an absent package
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in ("fastapi", "pydantic"):
                raise ModuleNotFoundError(f"No module named {name!r}", name=name)
            return None

    sys.meta_path.insert(0, _NoFastAPI())
"""
# captured on the base (b310de30), where ``import sharpit`` imported the adapter eagerly
STARLETTE_MAPPINGS = {
    "mappings": [
        {
            "consumes": None,
            "handler": "__main__:owners",
            "method": "GET",
            "pattern": "/owners/{owner}",
            "produces": None,
        }
    ],
    "page": {"hasMore": False, "limit": 1, "matched": 1, "offset": 0, "returned": 1, "total": 1},
    "total": 1,
}


def _python(script: str, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        env=os.environ | env,
        check=False,
    )


def _last_json(done: subprocess.CompletedProcess[str]) -> object:
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_import_sharpit_does_not_import_fastapi_or_the_adapter() -> None:
    loaded = _last_json(
        _python(
            """
            import json, sys
            import sharpit
            print(json.dumps({name: name in sys.modules for name in ("fastapi", "pydantic", "sharpit.fastapi")}))
            """
        )
    )

    assert loaded["fastapi"] is False  # pyright: ignore[reportIndexIssue]
    assert loaded["pydantic"] is False  # pyright: ignore[reportIndexIssue]
    assert loaded["sharpit.fastapi"] is False  # pyright: ignore[reportIndexIssue]


def test_the_public_names_resolve_lazily_and_dir_lists_them() -> None:
    facts = _last_json(
        _python(
            """
            import json
            import sharpit
            from sharpit.engine.capture.securitylogs import record_security_event
            from sharpit.fastapi.adapter import install
            from sharpit.fastapi.sources import attach_sql_sources, detach_sql_sources

            star = {}
            exec("from sharpit import *", star)
            try:
                sharpit.typo
            except AttributeError as error:
                missing = str(error)
            print(json.dumps({
                "all": sharpit.__all__,
                "dir": sorted(set(sharpit.__all__) - set(dir(sharpit))),
                "star": sorted(set(sharpit.__all__) - set(star)),
                "same": [
                    sharpit.install is install,
                    sharpit.attach_sql_sources is attach_sql_sources,
                    sharpit.detach_sql_sources is detach_sql_sources,
                    sharpit.record_security_event is record_security_event,
                ],
                "missing": missing,
            }))
            """
        )
    )

    assert facts["all"] == [  # pyright: ignore[reportIndexIssue]
        "__version__",
        "attach_sql_sources",
        "detach_sql_sources",
        "install",
        "record_security_event",
    ]
    assert facts["dir"] == []  # pyright: ignore[reportIndexIssue]
    assert facts["star"] == []  # pyright: ignore[reportIndexIssue]
    assert facts["same"] == [True, True, True, True]  # pyright: ignore[reportIndexIssue]
    assert facts["missing"] == "module 'sharpit' has no attribute 'typo'"  # pyright: ignore[reportIndexIssue]


def test_without_fastapi_a_starlette_install_introspects_as_before(tmp_path: Path) -> None:
    report = _last_json(
        _python(
            textwrap.dedent(BLOCK_FASTAPI)
            + textwrap.dedent(
                """
                import json
                import sharpit
                from starlette.applications import Starlette
                from starlette.responses import PlainTextResponse
                from starlette.routing import Route
                from starlette.testclient import TestClient

                async def owners(_):
                    return PlainTextResponse("ok")

                app = Starlette(routes=[Route("/owners/{owner}", owners)])
                sharpit.install(app, enabled="ON", show_banner=False)
                client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
                print(json.dumps(client.get("/sharpit/api/mappings/flat").json()))
                """
            ),
            SHARPIT_STATE_DIR=str(tmp_path / "state"),
        )
    )

    assert report == STARLETTE_MAPPINGS


def test_pyright_rejects_an_unknown_sharpit_name(tmp_path: Path) -> None:
    pytest.importorskip("pyright", reason="pyright is a dev-group tool; the lowest-direct leg syncs --no-dev")
    probe = tmp_path / "probe.py"
    probe.write_text("from sharpit import install, typo\n\nreveal_type(install)\nprint(typo)\n", encoding="utf-8")

    done = subprocess.run(
        [sys.executable, "-m", "pyright", "--outputjson", "--pythonpath", sys.executable, str(probe)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    diagnostics = json.loads(done.stdout)["generalDiagnostics"]
    rules = [(d.get("rule"), d["message"]) for d in diagnostics]

    assert ("reportAttributeAccessIssue", '"typo" is unknown import symbol') in rules
    assert any("-> SharpitHandle" in message for _, message in rules), rules
