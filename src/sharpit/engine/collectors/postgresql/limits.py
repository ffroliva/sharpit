"""PostgreSQL row limits, timeouts and read-one-past truncation helper."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sharpit.settings import SharpitSettings

STATEMENT_TIMEOUT = 5.0
LOCK_TIMEOUT = 2.0
READ_BUDGET = 15.0
MAX_ROW_LIMIT = 2_147_483_646


@dataclass(frozen=True)
class RowLimits:
    max_sessions: int = 0
    max_statements: int = 0
    max_indexes: int = 0
    max_tables: int = 0
    max_vacuum_tables: int = 0
    max_replicas: int = 0
    max_settings: int = 0

    @classmethod
    def from_settings(cls, settings: SharpitSettings) -> RowLimits:
        del settings
        return cls()

    def to_dto(self) -> dict[str, int]:
        return {
            "maxSessions": self.max_sessions,
            "maxStatements": self.max_statements,
            "maxIndexes": self.max_indexes,
            "maxTables": self.max_tables,
            "maxVacuumTables": self.max_vacuum_tables,
            "maxReplicas": self.max_replicas,
            "maxSettings": self.max_settings,
        }


def read_one_past[T](rows: Sequence[T], limit: int) -> tuple[list[T], bool]:
    del limit
    return list(rows), False
