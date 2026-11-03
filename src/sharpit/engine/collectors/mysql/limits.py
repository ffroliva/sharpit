"""MySQL row limits, timeouts and read-one-past truncation helper."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, fields
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sharpit.settings import SharpitSettings

STATEMENT_TIMEOUT = 5.0
LOCK_TIMEOUT = 2.0
READ_BUDGET = 15.0
MAX_ROW_LIMIT = 2_147_483_646


def _validate_limit(value: int, name: str) -> int:
    if isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be >= 1")
    if value > MAX_ROW_LIMIT:
        raise ValueError(f"{name} must be <= {MAX_ROW_LIMIT}")
    return value


@dataclass(frozen=True)
class RowLimits:
    max_sessions: int = 100
    max_statements: int = 100
    max_indexes: int = 500
    max_tables: int = 200
    max_lock_waits: int = 100
    max_replication_channels: int = 10
    max_settings: int = 40

    def __post_init__(self) -> None:
        for f in fields(self):
            _validate_limit(getattr(self, f.name), f.name)

    @classmethod
    def from_settings(cls, settings: SharpitSettings) -> RowLimits:
        return cls(
            max_sessions=settings.mysql_max_sessions,
            max_statements=settings.mysql_max_statements,
            max_indexes=settings.mysql_max_indexes,
            max_tables=settings.mysql_max_tables,
            max_lock_waits=settings.mysql_max_lock_waits,
            max_replication_channels=settings.mysql_max_replication_channels,
            max_settings=settings.mysql_max_settings,
        )

    def to_dto(self) -> dict[str, int]:
        return {
            "maxSessions": self.max_sessions,
            "maxStatements": self.max_statements,
            "maxIndexes": self.max_indexes,
            "maxTables": self.max_tables,
            "maxLockWaits": self.max_lock_waits,
            "maxReplicationChannels": self.max_replication_channels,
            "maxSettings": self.max_settings,
        }


def read_one_past[T](rows: Sequence[T], limit: int) -> tuple[list[T], bool]:
    if len(rows) > limit:
        return list(rows[:limit]), True
    return list(rows), False
