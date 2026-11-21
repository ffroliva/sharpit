"""Safe projection of FastAPI request validation errors into BootUI diagnostics."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast, get_args, get_origin

from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from pydantic_core.core_schema import ErrorType
from starlette.routing import Match

MAX_DIAGNOSTICS = 10
MAX_FIELD_LENGTH = 256
_ERROR_TYPES = frozenset(get_args(ErrorType))


def validation_details(
    exc: BaseException, endpoint: Any, full: bool
) -> tuple[str | None, list[dict[str, object]], bool]:
    if not isinstance(exc, RequestValidationError):
        return None, [], False
    errors = cast(list[dict[str, Any]], exc.errors())
    fields = _model_fields(endpoint)
    rows: set[tuple[str | None, str, str]] = set()
    for error in errors:
        kind: object = error.get("type")
        loc: object = error.get("loc")
        reason = kind if isinstance(kind, str) and (kind in _ERROR_TYPES or full) else "Invalid"
        reason = _bounded(reason)
        path, extra = _field_path(loc, fields, full, kind)
        if extra:
            path = "\0" + path
        rows.add((_target_type(endpoint), _bounded(path), reason))
    ordered = sorted(rows, key=lambda row: (row[1], row[2], row[0] or ""))
    truncated = len(ordered) > MAX_DIAGNOSTICS
    diagnostics: list[dict[str, object]] = [
        {"targetType": target, "fieldPath": _exposed_path(path, full), "reason": reason}
        for target, path, reason in ordered[:MAX_DIAGNOSTICS]
    ]
    count = len(errors)
    message = f"{count} validation error{'s' if count != 1 else ''}"
    return message, diagnostics, truncated


def is_validation_error(exc: BaseException) -> bool:
    return isinstance(exc, RequestValidationError)


def route_for_scope(scope: object, app: Any = None) -> Any:
    if not isinstance(scope, dict):
        return None
    scope_dict = cast(dict[str, Any], scope)
    if (route := scope_dict.get("route")) is not None:
        return route
    try:
        host = app or scope_dict.get("app")
        if host is None:
            return None
        router: Any = host.router
        for route in router.routes:
            if getattr(route, "path", None) == scope_dict.get("path"):
                return route
            match, _ = route.matches(scope_dict)
            if match is Match.FULL:
                return route
    except Exception:
        return None
    return None


def _model_fields(route: Any) -> set[str] | None:
    try:
        dependant = route.dependant
        models = [p.field_info.annotation for p in dependant.body_params]
        fields = _parameter_fields(dependant)
        body_model = False
        seen: set[type] = set()
        while models:
            model = models.pop()
            if get_origin(model) is not None:
                models.extend(get_args(model))
                continue
            if not isinstance(model, type) or not issubclass(model, BaseModel) or model in seen:
                continue
            body_model = True
            seen.add(model)
            for name, field in model.model_fields.items():
                fields.add(name)
                if isinstance(field.alias, str):
                    fields.add(field.alias)
                if isinstance(field.validation_alias, str):
                    fields.add(field.validation_alias)
                models.append(field.annotation)
        if body_model:
            fields.add("\0body-model")
        return fields or None
    except Exception:
        return None


def _parameter_fields(dependant: Any) -> set[str]:
    fields: set[str] = set()
    for location in ("query", "path", "header", "cookie"):
        for field in getattr(dependant, f"{location}_params", ()):
            fields.add(f"{location}:{field.name}")
            if isinstance(field.alias, str):
                fields.add(f"{location}:{field.alias}")
    return fields


def _target_type(route: Any) -> str | None:
    try:
        for parameter in route.dependant.body_params:
            annotation = parameter.field_info.annotation
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                return annotation.__name__[:MAX_FIELD_LENGTH]
    except Exception:
        return None
    return None


def _field_path(loc: Any, fields: set[str] | None, full: bool, kind: object) -> tuple[str, bool]:
    if not isinstance(loc, (tuple, list)):
        return "(unknown)", False
    parts: list[Any] = list(cast(Sequence[Any], loc))
    if any(not isinstance(part, (str, int)) for part in parts):
        return "(unknown)", False
    prefix = ""
    if parts and parts[0] in ("body", "query", "path", "header", "cookie"):
        location = parts.pop(0)
        prefix = location
    if kind == "json_invalid":
        return "(body)", False
    body_model = fields is not None and "\0body-model" in fields
    if prefix == "body" and not body_model:
        path = prefix + "[*]" * len(parts)
        extra = kind == "extra_forbidden"
        return path, extra
    out: list[str] = [prefix] if prefix and prefix != "body" else []
    extra = False
    for part in parts:
        if isinstance(part, int) or part == "[key]":
            out.append("[*]")
        else:
            if part == "extra_forbidden":
                continue
            declared = _declared_field(fields, prefix, part)
            if fields is None or not declared:
                key = "".join(char if char.isprintable() else " " for char in part)
                key = key.replace("\\", "\\\\").replace("'", "\\'")[:64]
                extra = extra or kind == "extra_forbidden"
                out.append(key if kind == "extra_forbidden" else f"['{key}']" if full else "[*]")
            else:
                out.append(part)
    path = ".".join(out).replace(".[", "[") or "(body)"
    return path[:MAX_FIELD_LENGTH] + ("…" if len(path) > MAX_FIELD_LENGTH else ""), extra


def _declared_field(fields: set[str] | None, prefix: str, part: str) -> bool:
    if fields is None:
        return False
    return f"{prefix}:{part}" in fields if prefix != "body" else part in fields


def _exposed_path(path: str, full: bool) -> str:
    if path.startswith("\0"):
        return path[1:] if full else "(unrecognized property)"
    return path


def _bounded(value: str) -> str:
    return value[:MAX_FIELD_LENGTH] + ("…" if len(value) > MAX_FIELD_LENGTH else "")
