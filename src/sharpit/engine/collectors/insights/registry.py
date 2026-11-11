"""Runtime Insights kind registry: BootUI's 28 observations in report order (``RuntimeInsightsService.java:441-468``).

Each kind's id, title, tier and sources live in its own module under ``kinds/``, so a kind lane edits only that module
and flips its ``IMPLEMENTED`` flag; nothing here changes when a kind lands.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from types import ModuleType
from typing import Any

# BootUI CorrelationTier, strongest first (E/web/CorrelationTier.java)
TIERS = ("REQUEST_ID", "PROPAGATED", "TRACE_ID", "SERVING_THREAD", "TIME_WINDOW")

_ORDER = (
    "route_time_breakdown", "exception_hotspots", "errors_behind_2xx", "repeated_selects", "connections_per_request",
    "safe_method_dml", "proxy_bypass", "anonymous_data_reach", "anonymous_success_on_restricted_route",
    "split_transaction_writes", "unbatched_write_loop", "transactional_listener_skipped", "after_commit_writes",
    "orm_auto_flush", "large_persistence_context", "slow_flush", "connection_reacquisition",
    "readonly_candidate_transaction", "paged_without_order", "transaction_across_remote_call", "lazy_sql_after_handler",
    "event_loop_blocking", "gc_inflated_latency", "heap_growth_after_gc", "ai_usage_by_route",
    "framework_warnings_by_route", "work_after_response", "changed_code_not_executed",
)  # fmt: skip


@dataclass(frozen=True)
class KindSpec:
    kind: str
    title: str
    minimum_tier: str
    reads: frozenset[str]
    optional_reads: frozenset[str]
    module: ModuleType

    @property
    def evaluate(self) -> Any:
        """The kind module's ``evaluate(snapshot) -> Evaluation``, or ``None`` while the kind is a stub."""
        return getattr(self.module, "evaluate", None)

    @property
    def implemented(self) -> bool:
        """Read from the kind module at call time: a flip or a monkeypatch is seen everywhere."""
        return bool(self.module.IMPLEMENTED)


def _spec(name: str) -> KindSpec:
    module = import_module(f"{__package__}.kinds.{name}")
    return KindSpec(module.KIND, module.TITLE, module.MINIMUM_TIER, module.READS, module.OPTIONAL_READS, module)


KINDS: tuple[KindSpec, ...] = tuple(_spec(name) for name in _ORDER)
