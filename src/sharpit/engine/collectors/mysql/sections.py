"""The ``mysql`` panel sections and catalog collectors (BootUI 2.2.0 contract §6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sharpit.engine.collectors.mysql.limits import RowLimits
from sharpit.engine.masking import Masker

SECTION_IDS = (
    "sessions",
    "statements",
    "indexes",
    "tables",
    "lock-waits",
    "replication-channels",
    "settings",
)

Dto = dict[str, Any]


@dataclass
class DataSourceData:
    name: str
    database_name: str | None = None
    capabilities: Dto = field(default_factory=dict)
    sections: list[Dto] = field(default_factory=list)
    sessions: list[Dto] = field(default_factory=list)
    statements: list[Dto] = field(default_factory=list)
    indexes: list[Dto] = field(default_factory=list)
    tables: list[Dto] = field(default_factory=list)
    lock_waits: list[Dto] = field(default_factory=list)
    replication_channels: list[Dto] = field(default_factory=list)
    metrics: list[Dto] = field(default_factory=list)
    settings: list[Dto] = field(default_factory=list)
    diagnostics: list[Dto] = field(default_factory=list)
    truncated: bool = False


def collect_capabilities(_conn: Any, data: DataSourceData) -> Dto:
    caps = {
        "serverVersion": "",
        "serverComment": "",
        "isMariaDb": False,
        "performanceSchema": False,
    }
    data.capabilities = caps
    return caps


def collect_sessions(_conn: Any, _masker: Masker, _limits: RowLimits, _data: DataSourceData) -> Dto:
    return {
        "id": "sessions",
        "title": "Sessions",
        "status": "AVAILABLE",
        "reason": None,
        "hint": None,
        "rowCount": 0,
        "truncated": False,
    }


def collect_statements(_conn: Any, _masker: Masker, _limits: RowLimits, _data: DataSourceData) -> Dto:
    return {
        "id": "statements",
        "title": "Statements",
        "status": "AVAILABLE",
        "reason": None,
        "hint": None,
        "rowCount": 0,
        "truncated": False,
    }


def collect_indexes(_conn: Any, _limits: RowLimits, _data: DataSourceData) -> Dto:
    return {
        "id": "indexes",
        "title": "Indexes",
        "status": "AVAILABLE",
        "reason": None,
        "hint": None,
        "rowCount": 0,
        "truncated": False,
    }


def collect_tables(_conn: Any, _limits: RowLimits, _data: DataSourceData) -> Dto:
    return {
        "id": "tables",
        "title": "Tables",
        "status": "AVAILABLE",
        "reason": None,
        "hint": None,
        "rowCount": 0,
        "truncated": False,
    }


def collect_lock_waits(_conn: Any, _masker: Masker, _limits: RowLimits, _data: DataSourceData) -> Dto:
    return {
        "id": "lock-waits",
        "title": "Lock Waits",
        "status": "AVAILABLE",
        "reason": None,
        "hint": None,
        "rowCount": 0,
        "truncated": False,
    }


def collect_replication(_conn: Any, _limits: RowLimits, _data: DataSourceData) -> Dto:
    return {
        "id": "replication-channels",
        "title": "Replication Channels",
        "status": "AVAILABLE",
        "reason": None,
        "hint": None,
        "rowCount": 0,
        "truncated": False,
    }


def collect_settings(_conn: Any, _limits: RowLimits, _data: DataSourceData) -> Dto:
    return {
        "id": "settings",
        "title": "Settings",
        "status": "AVAILABLE",
        "reason": None,
        "hint": None,
        "rowCount": 0,
        "truncated": False,
    }


def collect_metrics(_conn: Any, _data: DataSourceData) -> list[Dto]:
    return []


def compare_changes(_previous: dict[str, Any] | None, _current: dict[str, Any]) -> list[Dto]:
    return []
