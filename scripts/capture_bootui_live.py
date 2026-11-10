"""Live BootUI 2.3.0 capture driven by routes.json with an allow-list."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

POST_ALLOW_LIST = (
    "/security/scan",
    "/architecture/scan",
    "/rest-api/scan",
    "/vulnerabilities/scan",
    "/database-advisor/scan",
    "/hibernate/scan",
    "/spring/scan",
    "/memory/scan",
    "/postgresql/read",
    "/mysql/read",
)


@dataclass(frozen=True)
class Step:
    phase: str
    method: str
    path: str
    panel: str
    sharpit_id: str
    name: str = "captured"


def build_plan(routes: dict[str, Any], ids: dict[str, str]) -> list[Step]:
    """Stub returning wrong value for red test."""
    return []


def run(
    plan: list[Step],
    opener: Any,
    raw_out: Path | str,
    base_url: str = "http://127.0.0.1:8080/bootui/api",
) -> dict[str, Any]:
    """Stub returning wrong value for red test."""
    return {}
