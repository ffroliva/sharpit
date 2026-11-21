"""Read Flask route metadata without calling application code."""

from __future__ import annotations

import re
from collections.abc import Iterable
from importlib.metadata import PackageNotFoundError, version
from types import FunctionType
from typing import cast

from flask import Flask
from sharpit.engine.spi import AppInfo, ProviderInfo, RouteInfo

_PARAMETER = re.compile(r"<(?:(?:[^<>:]+):)?([^<>:]+)>")


def _attribute(value: object, name: str) -> object | None:
    try:
        return getattr(value, name, None)
    except Exception:
        return None


def _handler_name(value: object) -> str | None:
    if type(value) is not FunctionType:
        return None
    module = _attribute(value, "__module__")
    qualname = _attribute(value, "__qualname__")
    if isinstance(module, str) and isinstance(qualname, str):
        return f"{module}:{qualname}"
    return None


class FlaskIntrospector:
    def __init__(self, app: object) -> None:
        self.app = app

    def app_info(self) -> AppInfo:
        values = vars(self.app) if isinstance(self.app, Flask) else {}
        title = values.get("import_name")
        try:
            flask_version = version("flask")
        except PackageNotFoundError:
            flask_version = None
        return AppInfo(title if isinstance(title, str) else None, "Flask", flask_version, None)

    def routes(self) -> list[RouteInfo]:
        values = vars(self.app) if isinstance(self.app, Flask) else {}
        url_map = values.get("url_map")
        raw_view_functions = values.get("view_functions")
        if url_map is None or type(raw_view_functions) is not dict:
            return []
        view_functions = cast(dict[str, object], raw_view_functions)
        try:
            rules = url_map.iter_rules()
            result: list[RouteInfo] = []
            for rule in rules:
                path = _attribute(rule, "rule")
                endpoint = _attribute(rule, "endpoint")
                methods = _attribute(rule, "methods")
                handler = _handler_name(view_functions.get(endpoint)) if isinstance(endpoint, str) else None
                if not isinstance(path, str) or handler is None:
                    continue
                method_values = (
                    cast(Iterable[object], methods) if isinstance(methods, (set, frozenset, list, tuple)) else ()
                )
                result.append(
                    RouteInfo(
                        tuple(sorted(method for method in method_values if isinstance(method, str))),
                        _PARAMETER.sub(r"{\1}", path),
                        handler,
                        None,
                        None,
                        None,
                        endpoint if isinstance(endpoint, str) else None,
                    )
                )
            return result
        except Exception:
            return []

    def providers(self) -> list[ProviderInfo]:
        return []
