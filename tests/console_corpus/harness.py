"""Build and record responses from an installed FastAPI console."""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
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
from sharpit.engine.collectors.vulns.inventory import Package
from sharpit.engine.sqla import listeners as _sqla_listeners

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
_FIXED_ENVIRONMENT = {
    "HOME": "/sharpit-home",
    "USERPROFILE": "/sharpit-home",
    "TMP": "/sharpit-tmp",
    "TEMP": "/sharpit-tmp",
    "PATH": "/sharpit/bin",
    "SHARPIT_TEST_API_TOKEN": "s3cr3t-value",
}
_FIXED_INVENTORY = (
    Package(name="fastapi", version="0.115.0", location=None),
    Package(name="packaging", version="24.0", location=None),
    Package(name="starlette", version="0.40.0", location=None),
)
_OPTIONAL_GATEKEEPER_PACKAGES = frozenset({"apscheduler", "arq", "celery", "prometheus_client", "sqlalchemy"})


@contextmanager
def isolated_sqlalchemy_state() -> Iterator[None]:
    """Run corpus requests without SQLAlchemy contexts left by earlier tests."""
    statement_contexts = tuple(_sqla_listeners._statement_contexts.values())
    discovery_contexts = tuple(_sqla_listeners._discovery_contexts.values())
    session_attached = _sqla_listeners._session
    routes = {context: _sqla_listeners.routed(context) for context in (*statement_contexts, *discovery_contexts)}
    _sqla_listeners.detach_all()
    try:
        yield
    finally:
        _sqla_listeners.detach_all()
        for context, (statements, discovery) in routes.items():
            _sqla_listeners.add(context, statements=statements, discovery=discovery)
        if session_attached:
            _sqla_listeners.attach_session()


def _is_optional_gatekeeper_module(name: str) -> bool:
    return (
        name.partition(".")[0] in _OPTIONAL_GATEKEEPER_PACKAGES
        or name == "opentelemetry.sdk"
        or name.startswith("opentelemetry.sdk.")
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
        "claude_code_session_state_dir": "~/claude-code-sessions",
        "copilot_session_state_dir": "~/copilot-sessions",
    }
    options.update(install_kwargs)
    sharpit.install(app, **options)
    return app


@contextmanager
def isolated_environment(temp_dir: str) -> Iterator[None]:
    """Keep corpus responses independent of host environment values."""
    del temp_dir
    tempfile.gettempdir()
    own_loggers = {
        name: logger
        for name, logger in logging.root.manager.loggerDict.items()
        if name == "sharpit" or name.startswith("sharpit.")
    }
    without_optional_modules = {
        name: module for name, module in sys.modules.items() if not _is_optional_gatekeeper_module(name)
    }
    with (
        patch.dict(os.environ, _FIXED_ENVIRONMENT, clear=True),
        patch.dict(logging.root.manager.loggerDict, own_loggers, clear=True),
        patch.dict(sys.modules, without_optional_modules, clear=True),
        patch("sharpit.engine.collectors.github.dashboard.detect_repository", return_value=_FIXED_REPOSITORY),
        patch("sharpit.engine.tools.inventory", return_value=list(_FIXED_INVENTORY)),
        patch("sharpit.engine.collectors.vulns.inventory.inventory", return_value=list(_FIXED_INVENTORY)),
    ):
        from sharpit.engine.collectors.config import config_report

        defaults = {**(config_report.__kwdefaults__ or {}), "environ": dict(_FIXED_ENVIRONMENT)}
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
