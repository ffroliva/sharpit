"""``GET/POST /sharpit/api/fastapi`` and the fastapi advisor's MCP/CLI tools (WAVE-B §1, §7; spec §4.4, §5.6).

The host app is a real package written to a temporary directory and imported, so the advisor resolves its root
through ``sys.modules`` (``appsource.resolve_package_root``) as it would for a deployed app.
"""

from __future__ import annotations

import builtins
import importlib
import io
import itertools
import json
import os
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import SideEffectGuard
from sharpit import install
from sharpit.engine import appsource

LOCAL = ("127.0.0.1", 50000)
URL = "/sharpit/api/fastapi"
SCAN = "/sharpit/api/fastapi/scan"
_COUNTER = itertools.count()

MAIN = """
import textwrap
import time

from fastapi import FastAPI

app = FastAPI(title="shop")


@app.get("/slow")
async def slow():
    time.sleep(1)
    return {"ok": True}


@app.get("/fine")
def fine() -> int:
    return 1


app.get("/library")(textwrap.dedent)
"""


@pytest.fixture
def app_pkg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Any, Path]]:
    name = f"fastapi_advisor_app_{next(_COUNTER)}"
    root = tmp_path / "src" / name
    root.mkdir(parents=True)
    (root / "__init__.py").write_text("", encoding="utf-8")
    (root / "main.py").write_text(textwrap.dedent(MAIN), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path / "src"))
    module = importlib.import_module(f"{name}.main")
    yield module.app, root
    for key in [k for k in sys.modules if k == name or k.startswith(f"{name}.")]:
        del sys.modules[key]


def _client(app: Any, state_dir: Path, **options: Any) -> TestClient:
    settings = {"enabled": "ON", "show_banner": False, "config_scan": False, "state_dir": str(state_dir), **options}
    install(app, **settings)
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False)


def _under(path: str, root: Path) -> bool:
    real = os.path.realpath(root)
    try:
        return os.path.commonpath([path, real]) == real
    except ValueError:
        return False


def test_scan_reads_only_app_package(
    app_pkg: tuple[Any, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, root = app_pkg
    client = _client(app, tmp_path / "state")
    opened: list[str] = []
    original = builtins.open

    def spy(file: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(file, str | os.PathLike):
            opened.append(os.path.realpath(os.fspath(file)))  # pyright: ignore[reportUnknownArgumentType]
        return original(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)
    monkeypatch.setattr(io, "open", spy)
    response = client.post(SCAN)
    sources = [path for path in opened if path.endswith(".py")]
    assert response.status_code == 200
    assert sources != []
    assert [path for path in sources if not _under(path, root)] == []


def test_scan_uses_the_one_resolver(app_pkg: tuple[Any, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # F5a-source: every advisor resolves the app's root through appsource.resolve_package_root, nothing else
    app, _ = app_pkg
    client = _client(app, tmp_path / "state")
    calls: list[object] = []
    original = appsource.resolve_package_root

    def spy(target: object, modules: Any, **kwargs: Any) -> Path | None:
        calls.append(target)
        return original(target, modules, **kwargs)

    monkeypatch.setattr(appsource, "resolve_package_root", spy)
    response = client.post(SCAN)
    assert response.status_code == 200
    assert calls == [app]


def test_scan_flags_blocking_call_and_pages_violations(app_pkg: tuple[Any, Path], tmp_path: Path) -> None:
    # ported: SpringScannerTests.scanReportsFindingsAcrossCategories
    app, _ = app_pkg
    client = _client(app, tmp_path / "state")
    response = client.post(SCAN)
    assert response.status_code == 200
    report = response.json()
    assert report["scan"]["status"] == "SCANNED"
    assert "FASTAPI-ASYNC-002" in {r["id"] for r in report["results"]}
    assert report["componentsAnalyzed"] == 2
    assert [line for line in report["evidence"]["limitations"] if "GET /library" in line] != []
    page = client.get(
        f"{URL}/rules/FASTAPI-ASYNC-002/violations", params={"scanId": report["violationDetails"]["scanId"]}
    )
    assert page.status_code == 200
    assert len(page.json()["violations"]) == 1
    assert client.get(URL).json() == report


def test_get_after_scan_opens_no_source_file(app_pkg: tuple[Any, Path], no_side_effects: SideEffectGuard) -> None:
    app, root = app_pkg
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    client = _client(app, no_side_effects.state_dir)
    with client:
        scanned = client.post(SCAN)
        assert scanned.status_code == 200
        no_side_effects.block_network()
        no_side_effects.rebaseline()  # the scan is a POST: it may read the app's source
        no_side_effects.watch_sources(root)
        report = client.get(URL)
        assert report.status_code == 200
        scan_id = report.json()["violationDetails"]["scanId"]
        page = client.get(f"{URL}/rules/FASTAPI-ASYNC-002/violations", params={"scanId": scan_id})
    assert page.status_code == 200
    assert no_side_effects.source_reads == []


def test_fastapi_get_no_side_effects(app_pkg: tuple[Any, Path], no_side_effects: SideEffectGuard) -> None:
    app, root = app_pkg
    no_side_effects.unblock_network()
    client = _client(app, no_side_effects.state_dir)
    with client:
        client.get("/sharpit/api/panels")
        no_side_effects.block_network()
        no_side_effects.rebaseline()
        no_side_effects.watch_sources(root)
        response = client.get(URL)
    assert response.status_code == 200
    assert response.json()["scan"]["status"] == "NOT_SCANNED"
    assert no_side_effects.violations == []
    assert no_side_effects.source_reads == []


def test_read_only_blocks_scan(app_pkg: tuple[Any, Path], tmp_path: Path) -> None:
    app, _ = app_pkg
    client = _client(app, tmp_path / "state", read_only=True)
    assert client.get(URL).status_code == 200
    assert client.post(SCAN).status_code == 403
    cli = client.post("/sharpit/api/cli/tools/fastapi_scan", content=b"{}")
    assert cli.status_code == 403
    assert client.get(URL).json()["scan"]["status"] == "NOT_SCANNED"


def test_inactive_fastapi_paths_404(app_pkg: tuple[Any, Path], tmp_path: Path) -> None:
    app, _ = app_pkg
    client = _client(app, tmp_path / "state", enabled="OFF")
    assert client.get(URL).status_code == 404
    assert client.post(SCAN).status_code == 404
    assert client.get(f"{URL}/rules/FASTAPI-ASYNC-002/violations", params={"scanId": "x"}).status_code == 404


def test_mcp_tools_list_has_only_get(app_pkg: tuple[Any, Path], tmp_path: Path) -> None:
    app, _ = app_pkg
    client = _client(app, tmp_path / "state", mcp_enabled="ON")
    listed = client.post(
        "/sharpit/api/mcp",
        content=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
        headers={"content-type": "application/json"},
    ).json()
    names = {tool["name"] for tool in listed["result"]["tools"] if "fastapi" in tool["name"]}
    assert "get_fastapi_report" in names
    assert "get_fastapi_rule_violations" in names
    assert "fastapi_scan" not in names


def test_cli_scan_runs_the_advisor(app_pkg: tuple[Any, Path], tmp_path: Path) -> None:
    app, _ = app_pkg
    client = _client(app, tmp_path / "state")
    response = client.post("/sharpit/api/cli/tools/fastapi_scan", content=b"{}")
    assert response.status_code == 200
    assert client.get(URL).json()["scan"]["status"] == "SCANNED"
