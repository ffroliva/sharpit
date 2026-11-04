"""``pip install sharpit`` with no ``[fastapi]`` extra (0.5.0 release council): plain Starlette, and the pytest plugin.

Each case runs in a clean interpreter, where ``sys.modules[name] = None`` makes the import fail as an absent package.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ABSENT = """
    import sys
    for name in ("fastapi", "pydantic"):  # pydantic only ever arrives with FastAPI
        sys.modules[name] = None
"""
PANELS = ("overview", "mappings", "beans", "fastapi", "fastapi-security", "security", "rest-api", "http-exchanges")


def _run(script: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    code = textwrap.dedent(ABSENT) + textwrap.dedent(script)
    return subprocess.run([sys.executable, "-c", code], cwd=cwd, capture_output=True, text=True, timeout=120)


def test_sharpit_imports_without_fastapi() -> None:
    done = _run("import sharpit; print('imported', sharpit.__version__)")
    assert done.stdout.startswith("imported"), done.stderr[-2000:]


def test_sharpit_installs_on_starlette_without_fastapi() -> None:
    done = _run(
        """
        import sharpit
        from starlette.applications import Starlette
        sharpit.install(Starlette(), enabled="ON", show_banner=False)
        print("installed")
        """
    )
    assert done.stdout.strip().endswith("installed"), done.stderr[-2000:]


def test_panels_answer_on_starlette_without_fastapi() -> None:
    done = _run(
        f"""
        import sharpit
        from starlette.applications import Starlette
        from starlette.responses import PlainTextResponse
        from starlette.routing import Route
        from starlette.testclient import TestClient

        async def owners(_):
            return PlainTextResponse("ok")

        app = Starlette(routes=[Route("/owners/{{owner}}", owners)])
        sharpit.install(app, enabled="ON", show_banner=False)
        client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
        client.get("/owners/1")
        print([client.get("/sharpit/api/" + panel).status_code for panel in {PANELS!r}])
        """
    )
    assert done.stdout.strip().splitlines()[-1:] == [str([200] * len(PANELS))], done.stderr[-2000:]


def test_the_pytest_plugin_loads_without_fastapi(tmp_path: Path) -> None:
    (tmp_path / "test_empty.py").write_text("def test_nothing():\n    pass\n", encoding="utf-8")
    done = _run(
        """
        import pytest
        sys.exit(pytest.main(["-q", "-p", "no:cacheprovider", "test_empty.py"]))
        """,
        tmp_path,
    )
    assert "Error while loading plugin" not in done.stdout + done.stderr


def test_the_pytest_session_passes_without_fastapi(tmp_path: Path) -> None:
    (tmp_path / "test_empty.py").write_text("def test_nothing():\n    pass\n", encoding="utf-8")
    done = _run(
        """
        import pytest
        sys.exit(pytest.main(["-q", "-p", "no:cacheprovider", "test_empty.py"]))
        """,
        tmp_path,
    )
    assert done.returncode == 0, (done.stdout + done.stderr)[-2000:]
