from __future__ import annotations

from typing import Any
from typing import Callable

from sharpit.engine.capture.streams import ChangeStream
from sharpit.engine.masking import Masker


class TransactionRecorder:
    def __init__(
        self,
        masker: Masker,
        *,
        max_entries: int = 200,
        slow_threshold_ms: int = 200,
        hold_threshold_ms: int = 500,
        recording: bool = True,
    ) -> None:
        self.changes = ChangeStream()

    def begin(
        self,
        key: int,
        *,
        parent: int | None,
        method: str,
        thread: str,
        trace_id: str | None,
        connection_id: str | None,
    ) -> int:
        return 0

    def end(self, entry_id: int, status: str, error: BaseException | None = None) -> None:
        return None

    def report(self, sql_rows: list[dict[str, Any]] | None) -> dict[str, Any]:
        return {"entries": []}

    def clear(self) -> None:
        return None

    def set_recording(self, enabled: bool) -> None:
        return None


def unavailable_report(reason: str) -> dict[str, Any]:
    return {"available": False, "unavailableReason": reason}


def tx_begin(conn: object) -> None:
    return None


def tx_commit(conn: object) -> None:
    return None


def tx_rollback(conn: object) -> None:
    return None


def tx_savepoint(conn: object, name: str | None) -> None:
    return None


def tx_rollback_savepoint(conn: object, name: str, context: object) -> None:
    return None


def tx_release_savepoint(conn: object, name: str, context: object) -> None:
    return None


def attach() -> Callable[[], None] | None:
    return None

