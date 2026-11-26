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


def mask_segments(path: str, masker: Masker) -> str:
    """Mask path segments that look like secrets or contain console tokens."""
    if not path:
        return path
    never_shown = getattr(masker, "_never_shown", ())
    if never_shown:
        path = "/".join(MASK if any(secret in seg for secret in never_shown) else seg for seg in path.split("/"))
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
    never_shown = getattr(masker, "_never_shown", ())
    if never_shown and any(secret in name for secret in never_shown):
        return MASK
    if is_secret_value(name):
        return MASK
    return name


def intake(masker: Masker) -> Callable[[Mapping[str, object]], dict[str, object]]:
    """Store intake function: masks targets and parameter names at intake."""
    never_shown = getattr(masker, "_never_shown", ())

    def _intake_row(row: Mapping[str, object]) -> dict[str, object]:
        out = dict(row)
        sensor = str(out.get("sensor") or out.get("source") or "")
        kind = str(out.get("kind") or "")

        target = out.get("target")
        if target is not None:
            target_str = str(target)
            if sensor == "files" or kind in ("file-path", "file path", "file"):
                out["target"] = mask_segments(target_str, masker)
            elif never_shown and any(secret in target_str for secret in never_shown):
                out["target"] = MASK
            else:
                out["target"] = target_str

        if sensor == "security-sinks" or "parameter" in out:
            param = cast("str | None", out.get("parameter"))
            out["parameter"] = display_parameter(param, masker)

        return out

    return _intake_row


def row_dto(row: StoreRow, masker: Masker) -> dict[str, object]:
    """Build the SideEffectsRowDto dict with exactly 26 keys in contract order."""
    never_shown = getattr(masker, "_never_shown", ())
    is_sinks = row.sensor == "security-sinks"
    is_files = row.sensor == "files"

    mapped_kind = "file path" if row.kind in ("file-path", "file path") else row.kind
    attribution = mask_segments(row.attribution, masker) if row.attribution else row.attribution

    if is_files or mapped_kind == "file path":
        target = mask_segments(row.target, masker) if row.target else row.target
    elif never_shown and row.target and any(s in row.target for s in never_shown):
        target = MASK
    else:
        target = row.target

    if is_sinks:
        param_val: str | None = display_parameter(row.parameter, masker) if row.parameter is not None else None
        if row.scope.lower() == "other":
            detail_val: str | None = wording.OTHER
        else:
            detail_val = wording.detail(mapped_kind, param_val, target, confirmed=row.confirmed)
    else:
        param_val = None
        detail_val = None

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
