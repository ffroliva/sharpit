"""The journal projected into one immutable snapshot (BootUI ``InsightsSnapshot``), copied before any kind runs.

``PRODUCED_SOURCES`` is the honesty gate: ``runtime_journal_sources`` lists all 23 BootUI sources, so "enabled" is not
"recorded". A source is recorded only when it is enabled **and** a merged producer publishes it; every kind that reads
an unproduced source answers not applicable, never "no eligible work". A producer lane adds its source here in the
same PR (``test_every_produced_source_has_a_producer_test``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sharpit.settings_registry import JOURNAL_SOURCES

PRODUCED_SOURCES: frozenset[str] = frozenset({"ai"})  # W7 A2's AI recognizer (#134); W5a's http and sql are not merged


@dataclass(frozen=True)
class Snapshot:
    status: Mapping[str, Any]
    records: Mapping[str, tuple[dict[str, object], ...]]  # recorded sources only
    newest_at: int | None = None

    def recorded(self, source: str) -> bool:
        return source in self.records

    def dropped(self, source: str) -> int:
        return int(self.status["dropped"].get(source, 0))


def project(journal: Any) -> Snapshot:
    """Copy what the journal holds in one lock acquisition (``view``): the window and the coverage never tear."""
    enabled = JOURNAL_SOURCES if journal.sources is None else journal.sources
    recorded = [s for s in JOURNAL_SOURCES if s in enabled and s in PRODUCED_SOURCES]
    status, records, newest = journal.view(recorded)
    return Snapshot(status, records, newest)
