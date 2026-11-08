"""FastAPI routes and MCP tools for the Architecture advisor (spec §4.4, §5.5)."""

from __future__ import annotations

import asyncio
import builtins
import contextlib
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.mcp import McpServer

LOCAL = ("127.0.0.1", 50000)


@pytest.fixture(scope="module")
def asgi_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


def _write(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_package_root_from_factory_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg = tmp_path / "factory_app"
    _write(pkg / "__init__.py")
    _write(pkg / "api.py", "from fastapi import FastAPI\napp = FastAPI()\n")
    monkeypatch.syspath_prepend(str(tmp_path))

    mod_init = types.ModuleType("factory_app")
    mod_init.__file__ = str(pkg / "__init__.py")
    mod_init.__path__ = [str(pkg)]

    app = FastAPI()
    mod_api = types.ModuleType("factory_app.api")
    mod_api.__file__ = str(pkg / "api.py")
    mod_api.app = app

    monkeypatch.setitem(sys.modules, "factory_app", mod_init)
    monkeypatch.setitem(sys.modules, "factory_app.api", mod_api)

    install(app, enabled="ON", show_banner=False, config_scan=False)
    client = TestClient(app, base_url="http://localhost", client=LOCAL)

    resp = client.post("/sharpit/api/architecture/scan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["scan"]["status"] == "SCANNED"
    assert "factory_app" in data["basePackages"]


def test_main_module_app_not_scanned_through_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main_mod = types.ModuleType("__main__")
    app = FastAPI()
    main_mod.app = app  # pyright: ignore[reportAttributeAccessIssue]
    main_mod.__file__ = str(tmp_path / "run.py")
    main_mod.__package__ = None
    monkeypatch.setitem(sys.modules, "__main__", main_mod)

    install(app, enabled="ON", show_banner=False, config_scan=False)
    client = TestClient(app, base_url="http://localhost", client=LOCAL)

    resp = client.post("/sharpit/api/architecture/scan")
    assert resp.status_code == 200
    data = resp.json()
    assert data["scan"]["status"] == "NOT_SCANNED"
    assert "not scanned" in data["scan"]["message"].lower()


def test_bounded_files_and_symlinks(tmp_path: Path) -> None:
    pkg = tmp_path / "sym_app"
    _write(pkg / "__init__.py")
    _write(pkg / "mod.py", "A = 1\n")
    outside = tmp_path / "outside_dir"
    _write(outside / "secret.py", "SECRET = 42\n")

    if sys.platform == "win32":
        import _winapi  # noqa: PLC0415

        _winapi.CreateJunction(str(outside), str(pkg / "jlink"))
    else:
        with contextlib.suppress(OSError):
            (pkg / "slink").symlink_to(outside, target_is_directory=True)

    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False, app_package=str(pkg))
    client = TestClient(app, base_url="http://localhost", client=LOCAL)

    resp = client.post("/sharpit/api/architecture/scan")
    assert resp.status_code == 200
    data = resp.json()
    assert not any("secret" in str(r).lower() for r in data["results"])
    assert not any("secret" in str(v).lower() for v in data.get("violationDetails", {}).get("records", []))


def test_get_after_scan_opens_no_source_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg = tmp_path / "open_app"
    _write(pkg / "__init__.py")
    _write(pkg / "mod.py", "B = 2\n")

    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False, app_package=str(pkg))
    client = TestClient(app, base_url="http://localhost", client=LOCAL)

    scan_resp = client.post("/sharpit/api/architecture/scan")
    assert scan_resp.status_code == 200

    opened: list[str] = []
    real_open = builtins.open

    def spy_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        opened.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy_open)

    get_resp = client.get("/sharpit/api/architecture")
    assert get_resp.status_code == 200
    assert not any(p.endswith(".py") for p in opened)


def test_scan_reads_only_app_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "target_pkg"
    _write(target / "__init__.py")
    _write(target / "mod.py", "C = 3\n")
    other = tmp_path / "other_pkg"
    _write(other / "__init__.py")
    _write(other / "mod.py", "D = 4\n")

    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False, app_package=str(target))
    client = TestClient(app, base_url="http://localhost", client=LOCAL)

    opened: list[str] = []
    real_open = builtins.open

    def spy_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        if str(file).endswith(".py"):
            opened.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy_open)

    resp = client.post("/sharpit/api/architecture/scan")
    assert resp.status_code == 200
    target_resolved = target.resolve()
    assert all(Path(p).resolve().is_relative_to(target_resolved) for p in opened)


def test_read_only_blocks_scan() -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False, read_only=True)
    client = TestClient(app, base_url="http://localhost", client=LOCAL)

    resp = client.post("/sharpit/api/architecture/scan")
    assert resp.status_code == 403
    assert resp.json().get("panel") == "architecture"


def test_inactive_architecture_paths_404() -> None:
    app_active = FastAPI()
    install(app_active, enabled="ON", show_banner=False, config_scan=False)
    client_active = TestClient(app_active, base_url="http://localhost", client=LOCAL)
    assert client_active.get("/sharpit/api/architecture").status_code == 200

    app_inactive = FastAPI()
    install(app_inactive, enabled="OFF", show_banner=False, config_scan=False)
    client_inactive = TestClient(app_inactive, base_url="http://localhost", client=LOCAL)
    assert client_inactive.get("/sharpit/api/architecture").status_code == 404
    assert client_inactive.post("/sharpit/api/architecture/scan").status_code == 404
    assert client_inactive.get("/sharpit/api/architecture/rules/ARCH-PKG-001/violations").status_code == 404


def test_architecture_get_no_side_effects(
    no_side_effects: Any, asgi_loop: asyncio.AbstractEventLoop, tmp_state_dir: Path
) -> None:
    del no_side_effects
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False, state_dir=str(tmp_state_dir))

    async def fetch() -> list[httpx.Response]:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
            return [
                await client.get("/sharpit/api/architecture"),
                await client.get("/sharpit/api/architecture/rules/ARCH-PKG-001/violations"),
            ]

    rep, viol = asgi_loop.run_until_complete(fetch())
    assert rep.status_code == 200
    assert viol.status_code in (200, 400, 404)


def test_mcp_tools_list_has_only_get() -> None:
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, config_scan=False)
    server = McpServer(handle.context)
    tool_names = [t.name for t in server.tools if not t.action]

    assert "get_architecture_report" in tool_names
    assert "get_architecture_rule_violations" in tool_names
    assert "architecture_scan" not in tool_names
    assert any(t.name == "architecture_scan" and t.action for t in server.tools)
