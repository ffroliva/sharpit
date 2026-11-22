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
        rows.add(_diagnostic_row(error, endpoint, fields, full))
    ordered = sorted(rows, key=lambda row: (row[1], row[2], row[0] or ""))
    truncated = len(ordered) > MAX_DIAGNOSTICS
    diagnostics: list[dict[str, object]] = [
        {"targetType": target, "fieldPath": _exposed_path(path, full), "reason": reason}
        for target, path, reason in ordered[:MAX_DIAGNOSTICS]
    ]
    count = len(errors)
    message = f"{count} validation error{'s' if count != 1 else ''}"
    return message, diagnostics, truncated


def _diagnostic_row(
    error: dict[str, Any], endpoint: Any, fields: set[str] | None, full: bool
) -> tuple[str | None, str, str]:
    kind: object = error.get("type")
    reason = kind if isinstance(kind, str) and (kind in _ERROR_TYPES or full) else "Invalid"
    path, extra = _field_path(error.get("loc"), fields, full, kind)
    if extra:
        path = "\0" + path
    return _target_type(endpoint), _bounded(path), _bounded(reason)


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
        fields = _parameter_fields(dependant)
        if _collect_body_model_fields(dependant.body_params, fields):
            fields.add("\0body-model")
        return fields or None
    except Exception:
        return None


def _collect_body_model_fields(body_params: Sequence[Any], fields: set[str]) -> bool:
    models: list[tuple[Any, tuple[str, ...], frozenset[type[BaseModel]]]] = [
        (parameter.field_info.annotation, ("body",), frozenset()) for parameter in body_params
    ]
    body_model = False
    while models:
        model, parent, ancestors = models.pop()
        if get_origin(model) is not None:
            models.extend((arg, parent, ancestors) for arg in get_args(model))
            continue
        if not isinstance(model, type) or not issubclass(model, BaseModel) or model in ancestors:
            continue
        body_model = True
        ancestors = ancestors | {model}
        for name, field in model.model_fields.items():
            _append_model_fields(field, name, parent, ancestors, fields, models)
    return body_model


def _append_model_fields(
    field: Any,
    name: str,
    parent: tuple[str, ...],
    ancestors: frozenset[type[BaseModel]],
    fields: set[str],
    models: list[tuple[Any, tuple[str, ...], frozenset[type[BaseModel]]]],
) -> None:
    names = {name}
    if isinstance(field.alias, str):
        names.add(field.alias)
    if isinstance(field.validation_alias, str):
        names.add(field.validation_alias)
    for field_name in names:
        child_path = (*parent, field_name)
        fields.add("/".join(child_path))
        models.append((field.annotation, child_path, ancestors))


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
    prefix = parts.pop(0) if parts and parts[0] in ("body", "query", "path", "header", "cookie") else ""
    if kind == "json_invalid":
        return "(body)", False
    body_model = fields is not None and "\0body-model" in fields
    if prefix == "body" and not body_model:
        path = prefix + "[*]" * len(parts)
        extra = kind == "extra_forbidden"
        return path, extra
    return _model_field_path(parts, fields, prefix, full, kind)


def _model_field_path(
    parts: list[Any], fields: set[str] | None, prefix: str, full: bool, kind: object
) -> tuple[str, bool]:
    out: list[str] = [prefix] if prefix and prefix != "body" else []
    parent = [prefix] if prefix else []
    extra = False
    for part in parts:
        rendered, is_extra = _field_path_part(part, fields, prefix, parent, full, kind)
        if rendered:
            out.append(rendered)
        extra = extra or is_extra
    path = ".".join(out).replace(".[", "[") or "(body)"
    return path[:MAX_FIELD_LENGTH] + ("…" if len(path) > MAX_FIELD_LENGTH else ""), extra


def _field_path_part(
    part: str | int, fields: set[str] | None, prefix: str, parent: list[str], full: bool, kind: object
) -> tuple[str, bool]:
    if isinstance(part, int) or part == "[key]":
        return "[*]", False
    if part == "extra_forbidden":
        return "", False
    declared = _declared_field(fields, prefix, part, parent)
    if fields is None or not declared:
        key = "".join(char if char.isprintable() else " " for char in part)
        key = key.replace("\\", "\\\\").replace("'", "\\'")[:64]
        if kind == "extra_forbidden":
            rendered = key
        elif full:
            rendered = f"['{key}']"
        else:
            rendered = "[*]"
        extra = kind == "extra_forbidden"
    else:
        rendered = part
        extra = False
    parent.append(part)
    return rendered, extra


def _declared_field(fields: set[str] | None, prefix: str, part: str, parent: list[str]) -> bool:
    if fields is None:
        return False
    return f"{prefix}:{part}" in fields if prefix != "body" else "/".join((*parent, part)) in fields


def _exposed_path(path: str, full: bool) -> str:
    if path.startswith("\0"):
        return path[1:] if full else "(unrecognized property)"
    return path


def _bounded(value: str) -> str:
    return value[:MAX_FIELD_LENGTH] + ("…" if len(value) > MAX_FIELD_LENGTH else "")
