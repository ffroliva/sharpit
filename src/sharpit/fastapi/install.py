"""Capture setup performed while installing sharpit on a host application."""

from __future__ import annotations

from typing import Any

from sharpit.engine import sqla
from sharpit.engine.capture.exceptions import ExceptionStore
from sharpit.engine.capture.exchanges import HttpExchangeBuffer
from sharpit.engine.capture.logtail import LogTailBuffer
from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.capture.streams import ChangeStream, StreamSlots
from sharpit.engine.context import SharpitContext
from sharpit.fastapi.capture import CaptureWiring
from sharpit.settings import SharpitSettings


def _configure_capture(app: Any, ctx: SharpitContext, settings: SharpitSettings) -> CaptureWiring:
    return None  # temporary red stub: restored by the foundation responsibility split


def install(*args: Any, **kwargs: Any) -> None:
    return None
