"""Build and record responses from an installed FastAPI console."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

from starlette.routing import Mount
from starlette.testclient import TestClient

import sharpit
from fastapi import FastAPI


def build_app(**install_kwargs: Any) -> FastAPI:
    """Install sharpit into a bare app with state confined to a temporary directory."""
    app = FastAPI()
    state_dir = install_kwargs.pop("state_dir", None)
    temporary_state = tempfile.TemporaryDirectory(prefix="sharpit-console-corpus-") if state_dir is None else None
    if temporary_state is not None:
        app.state.console_corpus_state = temporary_state
        state_dir = temporary_state.name
    options = {
        "enabled": "ON",
        "show_banner": False,
        "state_dir": str(state_dir),
        "claude_code_session_state_dir": str(Path(state_dir) / "claude-code-sessions"),
        "copilot_session_state_dir": str(Path(state_dir) / "copilot-sessions"),
    }
    options.update(install_kwargs)
    sharpit.install(app, **options)
    return app


@contextmanager
def isolated_environment(temp_dir: str) -> Iterator[None]:
    """Keep corpus responses clear of host environment values and retain the Windows runtime base paths."""
    system_root = os.environ.get("SYSTEMROOT", r"C:\Windows")
    environment = {"HOME": temp_dir, "USERPROFILE": temp_dir, "TMP": temp_dir, "TEMP": temp_dir}
    if os.name == "nt":
        environment.update(
            {"SystemRoot": system_root, "WINDIR": system_root, "PATH": str(Path(system_root) / "System32")}
        )
    with patch.dict(os.environ, environment, clear=True):
        from sharpit.engine.collectors.config import config_report

        defaults = {**(config_report.__kwdefaults__ or {}), "environ": dict(os.environ)}
        with patch.object(config_report, "__kwdefaults__", defaults):
            yield


def get_routes(app: FastAPI) -> list[tuple[str, str]]:
    """Return mounted API route methods and path templates from Starlette's live route table."""
    mount = next(
        (route for route in app.routes if isinstance(route, Mount) and route.path == "/sharpit"),
        None,
    )
    if mount is None:
        return []
    routes = getattr(mount.app, "routes", ())
    return sorted(
        (method, route.path)
        for route in routes
        if hasattr(route, "path") and route.path.startswith("/api")
        for method in getattr(route, "methods", ())
    )


def record(
    client: TestClient,
    method: str,
    path: str,
    headers: list[tuple[str, str]] | dict[str, str] | None = None,
) -> dict[str, Any]:
    """Record a response's status, stable transport headers, and decoded body."""
    response = client.request(method, path, headers=headers)
    selected_headers = {
        name: value
        for name, value in response.headers.items()
        if name.lower() in _CONTENT_HEADERS or name.lower() in _SECURITY_HEADERS
    }
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text
    return {"status": response.status_code, "headers": dict(sorted(selected_headers.items())), "body": body}


def assert_corpus_match(actual: Any, expected: Any, context: str = "") -> None:
    assert actual == expected, context


_SECURITY_HEADERS = frozenset(
    {
        "content-security-policy",
        "permissions-policy",
        "pragma",
        "cache-control",
        "referrer-policy",
        "x-content-type-options",
        "x-frame-options",
    }
)
_CONTENT_HEADERS = frozenset({"content-type", "content-encoding", "content-disposition", "content-language"})
