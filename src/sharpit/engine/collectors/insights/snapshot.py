"""The journal projected into one immutable snapshot (BootUI ``InsightsSnapshot``), copied before any kind runs.

``PRODUCED_SOURCES`` is the honesty gate: ``runtime_journal_sources`` lists all 23 BootUI sources, so "enabled" is not
"recorded". A source is recorded only when it is enabled **and** a merged producer publishes it; every kind that reads
an unproduced source answers not applicable, never "no eligible work". A producer lane adds its source here in the
same PR (``test_every_produced_source_has_a_producer_test``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Any

from sharpit.settings_registry import JOURNAL_SOURCES

if TYPE_CHECKING:
    from sharpit.engine.collectors.insights.requests import Request, RequestIndex

# W7 A2 (#134), W5a P-http, P-sql, P-exception
PRODUCED_SOURCES: frozenset[str] = frozenset({"ai", "exception", "http", "sql"})


DEFAULT_AI_TOKEN_THRESHOLD = 8000  # AiUsageByRoute.DEFAULT_TOKEN_THRESHOLD


@dataclass(frozen=True)
class Snapshot:
    status: Mapping[str, Any]
    records: Mapping[str, tuple[dict[str, object], ...]]  # recorded sources only
    newest_at: int | None = None
    ai_token_threshold: int = DEFAULT_AI_TOKEN_THRESHOLD  # runtime_insights_ai_token_threshold, validated positive

    @cached_property
    def request_index(self) -> RequestIndex:
        """The http requests, projected once per snapshot however many kinds read them."""
        from sharpit.engine.collectors.insights.requests import RequestIndex  # noqa: PLC0415 - requests imports this

        return RequestIndex(self.records.get("http", ()))

    @property
    def requests(self) -> tuple[Request, ...]:
        return self.request_index.requests

    def recorded(self, source: str) -> bool:
        return source in self.records

    def dropped(self, source: str) -> int:
        return int(self.status["dropped"].get(source, 0))


def project(journal: Any, ai_token_threshold: int = DEFAULT_AI_TOKEN_THRESHOLD) -> Snapshot:
    """Copy what the journal holds in one lock acquisition (``view``): the window and the coverage never tear."""
    enabled = JOURNAL_SOURCES if journal.sources is None else journal.sources
    recorded = [s for s in JOURNAL_SOURCES if s in enabled and s in PRODUCED_SOURCES]
    status, records, newest = journal.view(recorded)
    return Snapshot(status, records, newest, ai_token_threshold)
