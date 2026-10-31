"""Framework-free capture state (spec §6): one ``CaptureState`` per installed context, filled task by task."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # later tasks add these modules; the adapter owns the wiring
    from sharpit.engine.capture.exceptions import ExceptionStore  # pyright: ignore[reportMissingImports, reportUnknownVariableType]
    from sharpit.engine.capture.exchanges import HttpExchangeBuffer
    from sharpit.engine.capture.logtail import LogTailBuffer  # pyright: ignore[reportMissingImports, reportUnknownVariableType]
    from sharpit.engine.capture.sqltrace import SqlTraceRecorder  # pyright: ignore[reportMissingImports, reportUnknownVariableType]
    from sharpit.engine.capture.streams import ChangeStream, StreamSlots  # pyright: ignore[reportMissingImports, reportUnknownVariableType]
    from sharpit.engine.sqla import EngineRegistry  # pyright: ignore[reportMissingImports, reportUnknownVariableType]
    from sharpit.fastapi.capture import CaptureWiring


@dataclass(eq=False)
class CaptureState:
    exchanges: HttpExchangeBuffer | None = None
    exceptions: ExceptionStore | None = None
    sql_trace: SqlTraceRecorder | None = None
    log_tail: LogTailBuffer | None = None
    stream_slots: StreamSlots | None = None
    engine_registry: EngineRegistry | None = None
    loop: asyncio.AbstractEventLoop | None = None
    wiring: CaptureWiring | None = None
    activity_changes: ChangeStream | None = None


def route_path(scope: Mapping[str, Any]) -> str:
    """Path below ``root_path`` (as Starlette's private ``get_route_path``): ``""`` for the bare mount path.

    Shared by ``SharpitMount``, the capture middleware's self-exclusion and the probe, so all three agree.
    """
    path: str = scope["path"]
    root_path: str = scope.get("root_path", "")
    if root_path and (path == root_path or path.startswith(root_path + "/")):
        return path[len(root_path) :]
    return path


def under(path: str, prefix: str) -> bool:
    """True when ``path`` is ``prefix`` itself or below it."""
    return path == prefix or path.startswith(prefix + "/")
