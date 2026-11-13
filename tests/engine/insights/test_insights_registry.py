"""Runtime Insights kind registry (W5c I0): BootUI's 28 observations, registered as stubs in report order.

Order: ``RuntimeInsightsService.defaultObservations`` (``E/insights/RuntimeInsightsService.java:441-468``). Each row is
``kind()``, ``title()``, ``minimumTier()``, ``reads()`` and ``optionalReads()`` of ``E/insights/<Kind>.java``;
``safe-method-dml`` and ``anonymous-data-reach`` take the non-Quarkus branch (no optional ORM read, plan OQ-I6).
"""

from __future__ import annotations

import pytest

from sharpit.engine.collectors.insights import registry
from sharpit.settings_registry import JOURNAL_SOURCES

REQ = "REQUEST_ID"
BOOTUI_KINDS = (
    ("route-time-breakdown", "Route time breakdown", REQ, {"http"},
     {"sql", "connection", "rest-client", "authorization", "ai", "orm", "messaging"}),
    ("exception-hotspots", "Exception hotspots", REQ, {"exception"}, set()),
    ("errors-behind-2xx", "Errors behind 2xx responses", REQ, {"http"},
     {"transaction", "exception", "log", "rest-client"}),  # BootUI also lists fault-tolerance: never read here
    ("repeated-selects", "Repeated SELECTs", REQ, {"sql"}, {"transaction"}),
    ("connections-per-request", "Connections held together", REQ, {"connection"}, set()),
    ("safe-method-dml", "Writes in GET requests", REQ, {"http", "sql"}, set()),
    ("proxy-bypass", "Proxy bypass", REQ, {"sql"}, {"transaction", "cache"}),
    ("anonymous-data-reach", "Anonymous writes", REQ, {"http", "sql", "authorization"}, set()),
    ("anonymous-success-on-restricted-route", "Anonymous success on a restricted route", REQ,
     {"http", "authorization"}, set()),
    ("split-transaction-writes", "Writes split across transactions", REQ, {"sql", "transaction"}, set()),
    ("unbatched-write-loop", "Unbatched write loops", REQ, {"sql"}, {"transaction"}),
    ("transactional-listener-skipped", "Transactional listeners skipped", REQ, {"app-event"}, set()),
    ("after-commit-writes", "Writes after commit", REQ, {"app-event", "sql", "transaction"}, set()),
    ("orm-auto-flush", "Hibernate auto-flushes", REQ, {"orm"}, set()),
    ("large-persistence-context", "Large persistence contexts", REQ, {"orm"}, set()),
    ("slow-flush", "Slow Hibernate flushes", REQ, {"orm"}, set()),
    ("connection-reacquisition", "Connections re-acquired in a session", REQ, {"orm"}, {"sql", "transaction"}),
    ("readonly-candidate-transaction", "Read-write transactions that only read", REQ,
     {"orm", "transaction", "sql"}, set()),
    ("paged-without-order", "Paged without ORDER BY", REQ, {"sql"}, set()),
    ("transaction-across-remote-call", "Transactions open across remote calls", REQ, {"transaction"},
     {"connection", "rest-client", "ai"}),
    ("lazy-sql-after-handler", "SQL after the handler returned", REQ, {"http", "sql"}, {"transaction"}),
    ("event-loop-blocking", "Blocking on event loops", REQ, {"sql"}, set()),
    ("gc-inflated-latency", "Pauses during slow requests", REQ, {"http", "gc", "resources"}, set()),
    ("heap-growth-after-gc", "Heap growth after GC", REQ, {"gc"}, set()),
    ("ai-usage-by-route", "AI usage by route", "TRACE_ID", {"ai"}, set()),
    ("framework-warnings-by-route", "Framework warnings by route", REQ, {"log"}, set()),
    ("work-after-response", "Work after the response", "PROPAGATED", {"http", "agent.executors"},
     {"sql", "rest-client", "messaging"}),
    ("changed-code-not-executed", "Changed code not executed", REQ, set(), set()),
)  # fmt: skip


def test_insights_registry_lists_28_kinds_in_bootui_order() -> None:
    assert [spec.kind for spec in registry.KINDS] == [row[0] for row in BOOTUI_KINDS]


def test_each_kind_copies_bootui_title_tier_and_sources() -> None:
    rows = [
        (spec.kind, spec.title, spec.minimum_tier, set(spec.reads), set(spec.optional_reads)) for spec in registry.KINDS
    ]
    assert rows == list(BOOTUI_KINDS)


def test_kind_sources_are_journal_sources_and_tiers_are_bootui_tiers() -> None:
    assert len(registry.KINDS) == 28
    sources = {source for spec in registry.KINDS for source in (*spec.reads, *spec.optional_reads)}
    assert sources <= set(JOURNAL_SOURCES)
    assert {spec.minimum_tier for spec in registry.KINDS} <= set(registry.TIERS)


def test_kind_implemented_reads_the_kind_modules_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each kind lane flips only its own module's flag; the registry reads it at call time, as ``Panel.implemented``."""
    assert len(registry.KINDS) == 28
    spec = registry.KINDS[3]
    monkeypatch.setattr(spec.module, "IMPLEMENTED", True)
    assert spec.implemented is True
    monkeypatch.setattr(spec.module, "IMPLEMENTED", False)
    assert spec.implemented is False
