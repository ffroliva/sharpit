"""``security`` advisor routes, MCP tools and CLI scan over a real FastAPI app (WAVE-B contract §1, §2)."""

from __future__ import annotations

import builtins
import importlib.util
import io
import os
import sys
import tokenize
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from conftest import get_paths
from fastapi import FastAPI
from sharpit import install
from sharpit.fastapi.introspector import FastApiIntrospector

API = "/sharpit/api/security"
MCP = "/sharpit/api/mcp"
LOCAL = ("127.0.0.1", 50000)


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)
    app.post("/items")(lambda: "created")
    return app


def client_for(app: Any = None, **options: Any) -> TestClient:
    app = app if app is not None else _app()
    install(app, enabled="ON", show_banner=False, config_scan=False, mcp_enabled="ON", cli_enabled=True, **options)
    return TestClient(app, base_url="http://localhost", client=LOCAL)


def _scan(client: TestClient) -> dict[str, Any]:
    response = client.post(f"{API}/scan")
    assert response.status_code == 200, response.text  # the scan route exists and answered before its body is read
    return response.json()


def _mcp(client: TestClient, method: str, params: dict[str, Any] | None = None) -> Any:
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return client.post(MCP, json=body).json()


def test_scan_through_the_route_finds_wildcard_credentials(tmp_path: Path):
    response = client_for(state_dir=str(tmp_path)).post(f"{API}/scan")
    assert response.status_code == 200
    assert "SEC-CORS-002" in [r["id"] for r in response.json()["results"]]


def test_get_renders_the_last_scan(tmp_path: Path):
    client = client_for(state_dir=str(tmp_path))
    before = client.get(API).json().get("scan", {}).get("status")
    scanned = _scan(client)
    after = client.get(API).json()
    assert before == "NOT_SCANNED"
    assert after["scan"]["scannedAt"] == scanned["scan"]["scannedAt"]


def test_violations_page_counts_the_rule_after_scan(tmp_path: Path):
    # supersedes test_violations_page_after_scan (red 0f50d8e read a key the page DTO does not have)
    client = client_for(state_dir=str(tmp_path))
    scan_id = _scan(client)["violationDetails"]["scanId"]
    response = client.get(f"{API}/rules/SEC-CORS-002/violations", params={"scanId": scan_id})
    assert response.status_code == 200
    assert response.json()["violationCount"] == 1


def test_get_after_scan_opens_no_source_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # ported: SecurityScannerTests.initialReportDoesNotInspectConfigurationBeforeExplicitScan (and after a scan).
    # Supersedes red 0f50d8e, which also counted the dismissal store's own state file (re-read on every render by
    # the shared advisor core): the GET reads no app source, lists no directory and runs no introspection.
    package = _source_package(tmp_path, monkeypatch, "getapp")
    client = client_for(state_dir=str(tmp_path / "state"), app_package="getapp")
    scan_id = _scan(client)["violationDetails"]["scanId"]
    root = os.path.realpath(package)
    touched: list[str] = []

    def spy(name: str, original: Any) -> Any:
        def call(*args: Any, **kwargs: Any) -> Any:
            target = args[0] if args else None
            if name in ("scandir", "security_model", "security_facts"):
                touched.append(name)
            elif isinstance(target, str | os.PathLike):
                path = os.path.realpath(os.fspath(target))  # pyright: ignore[reportUnknownArgumentType]
                if os.path.commonpath([path, root]) == root or path.endswith(".py"):
                    touched.append(f"{name} {path}")
            return original(*args, **kwargs)

        return call

    for owner, attr in ((builtins, "open"), (io, "open"), (tokenize, "open"), (os, "scandir")):
        monkeypatch.setattr(owner, attr, spy(attr, getattr(owner, attr)))
    for attr in ("security_model", "security_facts"):
        monkeypatch.setattr(FastApiIntrospector, attr, spy(attr, getattr(FastApiIntrospector, attr)))
    statuses = [
        client.get(API).status_code,
        client.get(f"{API}/rules/SEC-CORS-002/violations", params={"scanId": scan_id}).status_code,
    ]
    assert statuses == [200, 200]
    assert touched == []


def _source_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> Path:
    package = tmp_path / name
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "settings.py").write_text("import os" + chr(10), encoding="utf-8")
    module = ModuleType(name)
    module.__file__ = str(package / "__init__.py")
    module.__path__ = [str(package)]
    monkeypatch.setitem(sys.modules, name, module)
    return package


def test_scan_reads_only_app_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    package = tmp_path / "shopapp"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "settings.py").write_text('import os\nKEY = os.getenv("SECRET_KEY", "dev")\n', encoding="utf-8")
    module = ModuleType("shopapp")
    module.__file__ = str(package / "__init__.py")
    module.__path__ = [str(package)]
    monkeypatch.setitem(sys.modules, "shopapp", module)
    state = tmp_path / "state"
    client = client_for(state_dir=str(state), app_package="shopapp")
    read: list[str] = []

    def spy(original: Any) -> Any:
        def call(file: Any, *args: Any, **kwargs: Any) -> Any:
            if isinstance(file, str | os.PathLike):
                read.append(os.path.realpath(os.fspath(file)))  # pyright: ignore[reportUnknownArgumentType]
            return original(file, *args, **kwargs)

        return call

    for owner, attr in ((builtins, "open"), (io, "open"), (tokenize, "open"), (os, "scandir")):
        monkeypatch.setattr(owner, attr, spy(getattr(owner, attr)))
    response = client.post(f"{API}/scan")
    root = os.path.realpath(package)
    outside = [p for p in read if os.path.commonpath([p, root]) != root and not p.startswith(os.path.realpath(state))]
    assert response.status_code == 200
    assert os.path.join(root, "settings.py") in read
    assert outside == []


def test_read_only_blocks_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # WAVE-B §2: read-only blocks the scan; GET and violations stay open
    global_client = client_for(state_dir=str(tmp_path / "a"), read_only=True)
    monkeypatch.setenv("SHARPIT_PANELS_SECURITY_READ_ONLY", "true")
    panel_client = client_for(state_dir=str(tmp_path / "b"))
    statuses = [
        global_client.post(f"{API}/scan").status_code,
        panel_client.post(f"{API}/scan").status_code,
        panel_client.get(API).status_code,
    ]
    assert statuses == [403, 403, 200]


def test_mcp_tools_list_has_only_get(tmp_path: Path):
    tools = _mcp(client_for(state_dir=str(tmp_path)), "tools/list")["result"]["tools"]
    names = sorted(t["name"] for t in tools if "security" in t["name"] and "fastapi" not in t["name"])
    assert names == ["get_security_report", "get_security_rule_violations"]


def test_mcp_report_and_violations(tmp_path: Path):
    client = client_for(state_dir=str(tmp_path))
    scan_id = _scan(client)["violationDetails"]["scanId"]
    report = _mcp(client, "tools/call", {"name": "get_security_report", "arguments": {}})
    page = _mcp(
        client,
        "tools/call",
        {"name": "get_security_rule_violations", "arguments": {"id": "SEC-CORS-002", "scanId": scan_id}},
    )
    assert "SEC-CORS-002" in report["result"]["content"][0]["text"]
    assert page["result"].get("isError") is not True


def test_cli_scan_tool(tmp_path: Path):
    response = client_for(state_dir=str(tmp_path)).post("/sharpit/api/cli/tools/security_scan", json={})
    assert response.status_code == 200
    assert "SEC-CORS-002" in response.text


def test_trap_route_untouched_by_every_introspecting_surface():
    # PLAN.md Review Focus 4: the shared trap test, run with this lane's surfaces (trap_surfaces_security.py)
    path = Path(__file__).parent / "test_introspection_trap.py"
    spec = importlib.util.spec_from_file_location("_trap_for_security", path)
    assert spec is not None
    assert spec.loader is not None
    trap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trap)
    assert "/sharpit/api/security" in get_paths()  # the route is mounted, so the sweep really reaches it
    assert "security_scan" in trap.CLI_TOOLS
    trap.test_trap_route_untouched_by_every_introspecting_surface()
