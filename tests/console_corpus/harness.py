"""Build and record responses from an installed FastAPI console."""

from __future__ import annotations

import tempfile
from typing import Any

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
    sharpit.install(app, enabled="ON", show_banner=False, state_dir=str(state_dir), **install_kwargs)
    return app


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
        if name.lower().startswith("content-") or name.lower() in _SECURITY_HEADERS
    }
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text
    return {"status": response.status_code, "headers": dict(sorted(selected_headers.items())), "body": body}


_SECURITY_HEADERS = frozenset(
    {
        "content-security-policy",
        "permissions-policy",
        "pragma",
        "referrer-policy",
        "x-content-type-options",
        "x-frame-options",
    }
)
