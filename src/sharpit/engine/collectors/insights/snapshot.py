"""The journal projected into one immutable snapshot (BootUI ``InsightsSnapshot``), copied before any kind runs.

``PRODUCED_SOURCES`` is the honesty gate: ``runtime_journal_sources`` lists all 23 BootUI sources, so "enabled" is not
"recorded". A source is recorded only when it is enabled **and** a merged producer publishes it; every kind that reads
an unproduced source answers not applicable, never "no eligible work". A producer lane adds its source here in the
same PR (``test_every_produced_source_has_a_producer_test``).

A produced source also counts as evidence only while its panel is enabled (BootUI ``InsightsSnapshot.available`` =
``records && visible``, ``JournalSourcePanels``): ``project`` leaves a hidden source out of ``records`` and names its
disabled panels in ``hidden``, so a disabled panel reads as absent evidence, never as proof that nothing happened.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Any

from sharpit.settings_registry import JOURNAL_SOURCES

if TYPE_CHECKING:
    from sharpit.engine.collectors.insights.requests import Request, RequestIndex

# W7 A2 (#134), W5a P-http, P-sql, P-exception, W7 E, P-log
PRODUCED_SOURCES: frozenset[str] = frozenset({"ai", "exception", "http", "log", "mail", "sql"})


# JournalSourcePanels.panelsOf (v2.3.0 :31-48) with sharpit's panel ids. A source whose BootUI panel sharpit lacks maps
# to its nearest panel, or to none (always visible): rest-client (no rest-client-trace panel), messaging (no broker
# panels), fault-tolerance, websocket; orm -> sqlalchemy-statistics; processes, files -> side-effects (sharpit's
# own mapping: BootUI 2.3.0 has no such sources). app-event,
# lifecycle, gc, resources own no panel in BootUI either.
SOURCE_PANELS: Mapping[str, tuple[str, ...]] = {
    "http": ("http-exchanges",), "sql": ("sql-trace",), "connection": ("sql-trace",),
    "transaction": ("transactions",), "exception": ("exceptions",), "agent.caught-exceptions": ("exceptions",),
    "security": ("security-logs",), "authorization": ("security-logs",), "cache": ("cache",),
    "scheduled": ("scheduled",), "log": ("log-tail",), "mail": ("email",), "ai": ("ai",),
    "orm": ("sqlalchemy-statistics",), "agent.executors": ("java-agent",),
    "processes": ("side-effects",), "files": ("side-effects",),
}  # fmt: skip
PanelEnabled = Callable[[str], bool]

DEFAULT_AI_TOKEN_THRESHOLD = 8000  # AiUsageByRoute.DEFAULT_TOKEN_THRESHOLD


@dataclass(frozen=True)
class Snapshot:
    status: Mapping[str, Any]
    records: Mapping[str, tuple[dict[str, object], ...]]  # recorded sources only
    newest_at: int | None = None
    ai_token_threshold: int = DEFAULT_AI_TOKEN_THRESHOLD  # runtime_insights_ai_token_threshold, validated positive
    hidden: Mapping[str, tuple[str, ...]] = field(
        default_factory=dict[str, tuple[str, ...]]
    )  # source -> its off panels

    @cached_property
    def request_index(self) -> RequestIndex:
        """The http requests, projected once per snapshot however many kinds read them."""
        from sharpit.engine.collectors.insights.requests import RequestIndex  # noqa: PLC0415 - requests imports this

        return RequestIndex(self.records.get("http", ()))

    @property
    def requests(self) -> tuple[Request, ...]:
        return self.request_index.requests

    def journaled(self, source: str) -> bool:
        """BootUI ``records``: the journal records ``source`` (a source with its panel off is still journaled)."""
        return source in self.records or source in self.hidden

    def available(self, source: str) -> bool:
        """BootUI ``available`` = ``records && visible``: journaled and its panel enabled."""
        return source in self.records

    def dropped(self, source: str) -> int:
        return int(self.status["dropped"].get(source, 0))


def hidden_panels(source: str, panel_enabled: PanelEnabled | None) -> tuple[str, ...]:
    """The panels owning ``source`` when none is enabled (BootUI ``visible`` false); empty when it is visible."""
    panels = SOURCE_PANELS.get(source, ())
    if panel_enabled is None or any(panel_enabled(p) for p in panels):
        return ()
    return panels


def project(
    journal: Any, ai_token_threshold: int = DEFAULT_AI_TOKEN_THRESHOLD, panel_enabled: PanelEnabled | None = None
) -> Snapshot:
    """Copy what the journal holds in one lock acquisition (``view``): the window and the coverage never tear.
    ``panel_enabled`` None: every panel is enabled."""
    enabled = JOURNAL_SOURCES if journal.sources is None else journal.sources
    produced = [s for s in JOURNAL_SOURCES if s in enabled and s in PRODUCED_SOURCES]
    hidden = {s: off for s in produced if (off := hidden_panels(s, panel_enabled))}
    status, records, newest = journal.view([s for s in produced if s not in hidden])
    return Snapshot(status, records, newest, ai_token_threshold, hidden)
