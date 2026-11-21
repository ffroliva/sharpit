"""Read Flask route metadata without calling application code."""

from __future__ import annotations

import inspect
import re
from collections.abc import Iterable
from importlib.metadata import PackageNotFoundError, version
from types import FunctionType
from typing import cast

from werkzeug.routing import Map

from flask import Flask
from sharpit.engine.spi import AppInfo, ProviderInfo, RouteInfo

_PARAMETER = re.compile(r"<(?:[^<>:]+:)?([^<>:]+)>")
_MISSING = object()


def _attribute(value: object, name: str) -> object | None:
    result = inspect.getattr_static(value, name, _MISSING)
    result_type = cast(type[object], type(result))
    if result is _MISSING or inspect.getattr_static(result_type, "__get__", _MISSING) is not _MISSING:
        return None
    return result


def _app_values(app: object) -> dict[str, object]:
    if not issubclass(type(app), Flask):
        return {}
    try:
        values = object.__getattribute__(app, "__dict__")
    except Exception:  # noqa: BLE001 - a slotted or unusual Flask subclass has no readable instance data
        return {}
    return cast(dict[str, object], values) if isinstance(values, dict) else {}


def _handler_name(value: object) -> str | None:
    if not callable(value):
        return None
    if type(value) is FunctionType:
        module = object.__getattribute__(value, "__module__")
        qualname = object.__getattribute__(value, "__qualname__")
        return f"{module}:{qualname}" if isinstance(module, str) and isinstance(qualname, str) else None
    target = type(value)
    module = type.__getattribute__(target, "__module__")
    qualname = type.__getattribute__(target, "__qualname__")
    if isinstance(module, str) and isinstance(qualname, str):
        return f"{module}:{qualname}"
    return None


class FlaskIntrospector:
    def __init__(self, app: object) -> None:
        self.app = app

    def app_info(self) -> AppInfo:
        values = _app_values(self.app)
        title = values.get("import_name")
        try:
            flask_version = version("flask")
        except PackageNotFoundError:
            flask_version = None
        return AppInfo(title if isinstance(title, str) else None, "Flask", flask_version, None)

    def routes(self) -> list[RouteInfo] | None:
        values = _app_values(self.app)
        url_map = values.get("url_map")
        raw_view_functions = values.get("view_functions")
        if type(url_map) is not Map or type(raw_view_functions) is not dict:
            return None
        view_functions = cast(dict[str, object], raw_view_functions)
        try:
            rules = Map.iter_rules(url_map)
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
            return None

    def providers(self) -> list[ProviderInfo]:
        return []
