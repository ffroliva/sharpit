"""Safe projection of FastAPI request validation errors into BootUI diagnostics."""

from __future__ import annotations

from typing import get_args

from fastapi.exceptions import RequestValidationError
from starlette.routing import Match
from pydantic import BaseModel
from pydantic_core import ErrorType

MAX_DIAGNOSTICS = 10
MAX_FIELD_LENGTH = 256
_ERROR_TYPES = frozenset(get_args(ErrorType))


def validation_details(exc: BaseException, endpoint: object, full: bool) -> tuple[str | None, list[dict[str, str | None]], bool]:
    if not isinstance(exc, RequestValidationError):
        return None, [], False
    errors = exc.errors()
    fields = _model_fields(endpoint)
    rows: set[tuple[str | None, str, str]] = set()
    for error in errors:
        kind = error.get("type")
        loc = error.get("loc")
        reason = kind if isinstance(kind, str) and (kind in _ERROR_TYPES or full) else "Invalid"
        reason = _bounded(reason)
        path, extra = _field_path(loc, fields, full, kind)
        if extra:
            path = "\0" + path
        rows.add((_target_type(endpoint), _bounded(path), reason))
    ordered = sorted(rows, key=lambda row: (row[1], row[2], row[0] or ""))
    truncated = len(ordered) > MAX_DIAGNOSTICS
    diagnostics = [
        {"targetType": target, "fieldPath": _exposed_path(path, full), "reason": reason}
        for target, path, reason in ordered[:MAX_DIAGNOSTICS]
    ]
    count = len(errors)
    message = f"{count} validation error{'s' if count != 1 else ''}"
    return message, diagnostics, truncated


def is_validation_error(exc: BaseException) -> bool:
    return isinstance(exc, RequestValidationError)


def route_for_scope(scope: object, app: object = None) -> object:
    if not isinstance(scope, dict):
        return None
    if (route := scope.get("route")) is not None:
        return route
    try:
        router = getattr(app or scope.get("app"), "router")
        for route in router.routes:
            if getattr(route, "path", None) == scope.get("path"):
                return route
            match, _ = route.matches(scope)
            if match is Match.FULL:
                return route
    except Exception:
        return None
    return None


def _model_fields(route: object) -> set[str] | None:
    try:
        dependant = getattr(route, "dependant")
        models = [p.type_ for p in dependant.body_params if isinstance(p.type_, type) and issubclass(p.type_, BaseModel)]
        fields = {"body"}
        fields.update(p.name for p in dependant.body_params)
        for model in models:
            for name, field in model.model_fields.items():
                fields.add(name)
                if isinstance(field.alias, str):
                    fields.add(field.alias)
                if isinstance(field.validation_alias, str):
                    fields.add(field.validation_alias)
        return fields if models else None
    except Exception:
        return None


def _target_type(route: object) -> str | None:
    try:
        for parameter in route.dependant.body_params:
            annotation = parameter.type_
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                return annotation.__name__[:MAX_FIELD_LENGTH]
    except Exception:
        return None
    return None


def _field_path(loc: object, fields: set[str] | None, full: bool, kind: object) -> tuple[str, bool]:
    if not isinstance(loc, (tuple, list)):
        return "(unknown)", False
    parts = list(loc)
    if parts and parts[0] in ("body", "query", "path", "header", "cookie"):
        parts = parts[1:]
    if kind == "json_invalid":
        return "(body)", False
    out: list[str] = []
    extra = False
    for part in parts:
        if isinstance(part, int):
            out.append("[*]")
        elif part == "[key]":
            out.append("[*]" if not full else "['key']")
        elif isinstance(part, str):
            if part in ("extra_forbidden",):
                continue
            if fields is None or part not in fields:
                extra = extra or kind == "extra_forbidden"
                key = part.replace("\\", "\\\\").replace("'", "\\'").replace("\r", " ").replace("\n", " ")[:64]
                out.append(f"['{key}']" if full else "[*]")
            else:
                out.append(part)
        else:
            out.append("[*]")
    path = ".".join(out).replace(".[*]", "[*]") or "(body)"
    return path[:MAX_FIELD_LENGTH] + ("…" if len(path) > MAX_FIELD_LENGTH else ""), extra


def _exposed_path(path: str, full: bool) -> str:
    if path.startswith("\0"):
        return path[1:] if full else "(unrecognized property)"
    return path


def _bounded(value: str) -> str:
    return value[:MAX_FIELD_LENGTH] + ("…" if len(value) > MAX_FIELD_LENGTH else "")
