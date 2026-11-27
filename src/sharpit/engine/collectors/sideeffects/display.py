"""Exposure-independent masking for side-effects rows."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, cast

from sharpit.engine.collectors.sideeffects import wording
from sharpit.engine.masking import is_secret_value
from sharpit.engine.sqltext import MASK

if TYPE_CHECKING:
    from sharpit.engine.collectors.sideeffects.store import StoreRow
    from sharpit.engine.masking import Masker

NAME_NOT_KEPT = "(name not kept)"
FILE_PATH = "file path"


def mask_segments(path: str, masker: Masker) -> str:
    """Mask path segments that look like secrets or contain console tokens."""
    if not path:
        return path
    if masker.holds_never_shown(path):
        path = "/".join(MASK if masker.holds_never_shown(seg) else seg for seg in path.split("/"))
    segments = path.split("/")
    masked = False
    for i, seg in enumerate(segments):
        if seg and seg != MASK and is_secret_value(seg):
            segments[i] = MASK
            masked = True
    return "/".join(segments) if masked else path


def display_parameter(name: str | None, masker: Masker) -> str:
    """Format and mask parameter name."""
    if name is None:
        return NAME_NOT_KEPT
    if masker.holds_never_shown(name):
        return MASK
    if is_secret_value(name):
        return MASK
    return name


def _display_target(target: str, *, is_path: bool, masker: Masker) -> str:
    if not target:
        return target
    if is_path:
        return mask_segments(target, masker)
    return MASK if masker.holds_never_shown(target) else target


def _sink_fields(row: StoreRow, mapped_kind: str, target: str, masker: Masker) -> tuple[str | None, str | None]:
    if row.sensor != "security-sinks":
        return None, None
    param = display_parameter(row.parameter, masker) if row.parameter is not None else None
    if row.scope.lower() == "other":
        return param, wording.OTHER
    return param, wording.detail(mapped_kind, param, target, confirmed=row.confirmed)


def intake(masker: Masker) -> Callable[[Mapping[str, object]], dict[str, object]]:
    """Store intake function: masks targets and parameter names at intake."""

    def _intake_row(row: Mapping[str, object]) -> dict[str, object]:
        out = dict(row)
        sensor = str(out.get("sensor") or out.get("source") or "")
        kind = str(out.get("kind") or "")

        target = out.get("target")
        if target is not None:
            is_path = sensor == "files" or kind in ("file-path", FILE_PATH, "file")
            out["target"] = _display_target(str(target), is_path=is_path, masker=masker)

        if sensor == "security-sinks" or "parameter" in out:
            param = cast("str | None", out.get("parameter"))
            out["parameter"] = display_parameter(param, masker)

        return out

    return _intake_row


def row_dto(row: StoreRow, masker: Masker) -> dict[str, object]:
    """Build the SideEffectsRowDto dict with exactly 26 keys in contract order."""
    is_files = row.sensor == "files"
    mapped_kind = FILE_PATH if row.kind in ("file-path", FILE_PATH) else row.kind
    attribution = mask_segments(row.attribution, masker) if row.attribution else row.attribution
    target = _display_target(row.target, is_path=(is_files or mapped_kind == FILE_PATH), masker=masker)
    param_val, detail_val = _sink_fields(row, mapped_kind, target, masker)
    origin_val = row.origin if is_files else None
    location_val = row.location if is_files else None

    return {
        "scope": row.scope,
        "attribution": attribution,
        "sensor": row.sensor,
        "kind": mapped_kind,
        "target": target,
        "callSite": row.call_site,
        "insideMethod": None,
        "origin": origin_val,
        "location": location_val,
        "count": row.count,
        "failed": row.failed,
        "completed": row.completed,
        "nonZeroExits": row.non_zero_exits,
        "lastExitStatus": row.last_exit_status,
        "totalMillis": row.total_millis,
        "maxMillis": row.max_millis,
        "firstSeen": row.first_seen,
        "lastSeen": row.last_seen,
        "exemplarRequestIds": list(row.exemplar_request_ids),
        "client": None,
        "capture": None,
        "capturedBy": None,
        "leftRunning": row.left_running,
        "requests": row.requests,
        "parameter": param_val,
        "detail": detail_val,
    }
