"""Build and record responses from an installed FastAPI console."""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import dotenv.main  # noqa: F401 - register third-party loggers before corpus isolation snapshots them
import packaging.tags  # noqa: F401
import pydantic_settings  # noqa: F401
from starlette.routing import Mount
from starlette.testclient import TestClient

import sharpit
import sharpit.fastapi.adapter  # noqa: F401
from fastapi import FastAPI
from sharpit.engine.collectors.github.detector import Repository

_FIXED_REPOSITORY = Repository(
    owner="ffroliva",
    name="sharpit",
    full_name="ffroliva/sharpit",
    host="github.com",
    api_base_uri="https://api.github.com/",
    html_url="https://github.com/ffroliva/sharpit",
    local_branch="main",
    upstream_branch=None,
)


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
    """Keep corpus responses independent of host environment values."""
    environment = {
        "HOME": temp_dir,
        "USERPROFILE": temp_dir,
        "TMP": temp_dir,
        "TEMP": temp_dir,
        "SHARPIT_TEST_API_TOKEN": "s3cr3t-value",
    }
    if os.name == "nt":
        # Python and Windows APIs require these base variables; their values are rooted in the isolated temp dir.
        environment.update({"SystemRoot": temp_dir, "WINDIR": temp_dir, "PATH": ""})
    own_loggers = {
        name: logger
        for name, logger in logging.root.manager.loggerDict.items()
        if name == "sharpit" or name.startswith("sharpit.")
    }
    with (
        patch.dict(os.environ, environment, clear=True),
        patch.dict(logging.root.manager.loggerDict, own_loggers, clear=True),
        patch("sharpit.engine.collectors.github.dashboard.detect_repository", return_value=_FIXED_REPOSITORY),
    ):
        from sharpit.engine.collectors.config import config_report

        defaults = {**(config_report.__kwdefaults__ or {}), "environ": dict(os.environ)}
        with patch.object(config_report, "__kwdefaults__", defaults):
            yield


def get_routes(app: FastAPI) -> list[tuple[str, str]]:
    """Return every mounted console route method and path template."""
    mount = next(
        (route for route in app.routes if isinstance(route, Mount) and route.path == "/sharpit"),
        None,
    )
    if mount is None:
        return []
    routes = getattr(mount.app, "routes", ())
    return sorted(
        (method, route.path) for route in routes if hasattr(route, "path") for method in getattr(route, "methods", ())
    )


def record(
    client: TestClient,
    method: str,
    path: str,
    headers: list[tuple[str, str]] | dict[str, str] | None = None,
) -> dict[str, Any]:
    """Record a response's status, non-volatile headers, and decoded body."""
    response = client.request(method, path, headers=headers)
    selected_headers = {
        name: value for name, value in response.headers.items() if name.lower() not in _VOLATILE_HEADERS
    }
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text
    return {"status": response.status_code, "headers": dict(sorted(selected_headers.items())), "body": body}


def assert_corpus_match(actual: Any, expected: Any, context: str = "") -> None:
    assert actual == expected, context


# These values vary by clock, server implementation, or response body length.
_VOLATILE_HEADERS = frozenset({"date", "server", "content-length"})
