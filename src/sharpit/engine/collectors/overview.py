"""``GET {api}/overview`` (port of BootUI ``OverviewDto``; spec 8 Overview)."""

from __future__ import annotations

import platform
import sys
from collections.abc import Mapping
from typing import Any

from sharpit import __version__
from sharpit.engine.context import SharpitContext


def _vendor() -> str:
    gil_enabled = getattr(sys, "_is_gil_enabled", lambda: True)()
    return platform.python_implementation() + ("" if gil_enabled else " (free-threaded)")


def overview_dto(ctx: SharpitContext, scope: Mapping[str, Any]) -> dict[str, Any]:
    info = ctx.introspector.app_info()
    server = scope.get("server")
    # app_root_path is the host's root_path; inside the mount root_path already ends with the sharpit path
    root = scope.get("app_root_path", scope.get("root_path"))
    return {
        "bootUiVersion": __version__,
        "applicationName": info.title or "application",
        "frameworkName": info.framework,
        "frameworkVersion": info.framework_version,
        "javaVersion": platform.python_version(),
        "javaVendor": _vendor(),
        "activeProfiles": list(ctx.profiles),
        "defaultProfiles": [],
        "webApplicationType": "ASGI",
        "serverPort": server[1] if server else None,
        "managementPort": None,
        "contextPath": root or None,
        "startupTimeMillis": ctx.startup_time_ms,
        "activation": ctx.activation.to_dto(),
        "openApiUrl": info.docs_url,
    }
