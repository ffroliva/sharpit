"""Runtime Insights I1: the snapshot over the journal, produced sources, checks, coverage and the report DTOs."""

from __future__ import annotations

import importlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from tests.overhead import check_wall_budget

from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights import snapshot as snapshot_module
from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.registry import KINDS, KindSpec
from sharpit.engine.collectors.insights.service import DISABLED, InsightsService, id_of
from sharpit.settings_registry import JOURNAL_SOURCES

AI = {"source": "ai", "operation": "chat", "inputTokens": 5, "outputTokens": 7}
NOT_RECORDED = "The runtime journal does not record the {} source (SHARPIT_RUNTIME_JOURNAL_SOURCES)."


@dataclass(frozen=True)
class FakeKind:
    kind: str = "uncounted-work"
    title: str = "Uncounted work"
    minimum_tier: str = "REQUEST_ID"
    reads: frozenset[str] = frozenset({"ai"})
    optional_reads: frozenset[str] = frozenset()
    evaluate: object = field(default=lambda _snapshot: Evaluation(0, []))


def _journal(sources: object = JOURNAL_SOURCES, **kwargs: int) -> RuntimeJournal:
    return RuntimeJournal(sources=sources, **kwargs)  # type: ignore[arg-type]


def _checks(journal: RuntimeJournal) -> dict[str, dict[str, object]]:
    return {check["kind"]: check for check in InsightsService(journal).report()["checks"]}


# ported: RuntimeInsightsServiceTests.anEmptySnapshotLeavesEveryCheckWithoutEligibleWork
def test_an_empty_snapshot_leaves_every_check_without_eligible_work() -> None:
    checks = InsightsService(_journal()).report()["checks"]
    assert len(checks) == 28
    assert {check["eligibleRequests"] for check in checks} == {0}
    assert {check["status"] for check in checks}.isdisjoint({"EVALUATED", "PARTIAL"})


# ported: RuntimeInsightsServiceTests.aZeroEligibleCheckPreservesTheExplanationOfUncountedWork
def test_a_zero_eligible_check_preserves_the_explanation_of_uncounted_work() -> None:
    journal = _journal()
    journal.offer(AI)
    kind = FakeKind(evaluate=lambda _s: Evaluation(0, [], "Recorded work could not be placed against its transaction."))
    check = InsightsService(journal, [kind]).report()["checks"][0]
    assert check["status"] == "INSUFFICIENT"
    assert check["eligibleRequests"] == 0
    assert "No eligible work was recorded" in check["reason"]
    assert "Recorded work could not be placed against its transaction." in check["reason"]


def test_enabled_but_unproduced_source_is_not_applicable() -> None:
    journal = _journal()
    journal.offer(AI)
    orm = _checks(journal)["orm-auto-flush"]
    assert orm["status"] == "NOT_APPLICABLE"
    assert orm["reason"] == NOT_RECORDED.format("orm")


def test_produced_sources_are_a_subset_of_the_journal_sources() -> None:
    assert snapshot_module.PRODUCED_SOURCES.issubset(JOURNAL_SOURCES)
    assert "ai" in snapshot_module.PRODUCED_SOURCES


def test_every_produced_source_has_a_producer_test() -> None:
    # a producer lane adds its source to PRODUCED_SOURCES and its (file, test function) row here in the same PR
    producer_tests = {"ai": ("tests/engine/capture/test_ai_journal.py", "test_ai_journal_event_is_metadata_only")}
    assert set(producer_tests) == snapshot_module.PRODUCED_SOURCES
    root = Path(__file__).resolve().parents[3]
    for source, (path, name) in producer_tests.items():
        file = root / path
        assert file.is_file(), f"{source}: {path} does not exist"
        assert f"def {name}(" in file.read_text(encoding="utf-8"), f"{source}: {name} is not in {path}"
        module = importlib.import_module(path.removesuffix(".py").replace("/", "."))
        marks = {m.name for m in getattr(getattr(module, name), "pytestmark", [])}
        assert marks.isdisjoint({"skip", "skipif", "xfail"}), f"{source}: {name} is skipped or xfailed"


def test_a_source_disabled_in_the_journal_is_not_recorded_even_when_produced() -> None:
    check = InsightsService(_journal(["http"]), [FakeKind()]).report()["checks"][0]
    assert check["status"] == "NOT_APPLICABLE"
    assert check["reason"] == NOT_RECORDED.format("ai")


def test_a_recorded_kind_without_an_evaluator_is_not_applicable_yet() -> None:
    journal = _journal()
    journal.offer(AI)
    check = InsightsService(journal, [FakeKind(evaluate=None)]).report()["checks"][0]
    assert check["status"] == "NOT_APPLICABLE"
    assert check["reason"] == "sharpit has not implemented this observation yet."


def test_a_recorded_kind_without_an_evaluator_in_the_real_registry_is_not_applicable_yet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(snapshot_module, "PRODUCED_SOURCES", frozenset(JOURNAL_SOURCES))
    stub = next(spec for spec in KINDS if spec.evaluate is None)
    journal = _journal()
    check = InsightsService(journal, [stub]).report()["checks"][0]
    assert check["kind"] == stub.kind
    assert check["status"] == "NOT_APPLICABLE"
    assert check["reason"] == "sharpit has not implemented this observation yet."


def test_a_finding_makes_the_check_evaluated_and_the_row_carries_the_listing() -> None:
    finding = Finding("k1", "GET /x", True, "3 of 4 requests.", 4, 3, ["look"], ["r1", "r2", "r3", "r4"], [], [], [])
    kind = FakeKind(kind="errors-behind-2xx", evaluate=lambda _s: Evaluation(4, [finding]))
    journal = _journal()
    journal.offer(AI)
    report = InsightsService(journal, [kind]).report()
    check = report["checks"][0]
    assert (check["status"], check["eligibleRequests"], check["findings"]) == ("EVALUATED", 4, 1)
    row = report["observations"][0]
    assert row["id"] == id_of("errors-behind-2xx", "k1")
    assert row["status"] == "OBSERVED"
    assert row["listed"] is True
    assert row["exemplarRequestIds"] == ["r1", "r2", "r3"]


def test_dropped_events_make_a_check_partial() -> None:
    journal = _journal(["ai"], max_bytes=1)
    journal.offer(AI)  # larger than the whole byte bound: counted as dropped under ai
    kind = FakeKind(evaluate=lambda _s: Evaluation(1, []))
    check = InsightsService(journal, [kind]).report()["checks"][0]
    assert check["status"] == "PARTIAL"
    assert "dropped 1 events this observation reads" in check["reason"]


def test_coverage_counts_events_by_how_they_link() -> None:
    journal = _journal()
    for extra in ({"requestId": "r"}, {"requestId": "r"}, {"executionId": "e"}, {"traceId": "t"}, {}):
        journal.offer({**AI, **extra})
    row = InsightsService(journal).report()["coverage"][0]
    # InsightsSnapshot.java:171-220: a trace-only event is byTraceId only when a retained request owns the trace; no
    # http request is retained here, so it is unlinked with the event that links to nothing
    assert row == {
        "source": "ai", "events": 5, "byRequestId": 2, "byExecutionId": 1, "byTraceId": 0, "unlinked": 2, "dropped": 0,
    }  # fmt: skip


def test_insights_report_evaluates_on_a_copy_without_holding_the_journal_lock() -> None:
    journal = _journal()
    journal.offer(AI)
    entered, release, done = threading.Event(), threading.Event(), threading.Event()

    def block(_snapshot: object) -> Evaluation:
        entered.set()
        assert release.wait(5)
        return Evaluation(0, [])

    worker = threading.Thread(target=InsightsService(journal, [FakeKind(evaluate=block)]).report)
    worker.start()
    try:
        assert entered.wait(5)
        threading.Thread(target=lambda: (journal.offer(AI), done.set())).start()
        assert done.wait(2), "offer blocked while a kind was evaluating"
    finally:
        release.set()
        worker.join(5)


def test_report_without_the_journal_is_unavailable() -> None:
    report = InsightsService(None).report()
    assert report["available"] is False
    assert report["unavailableReason"] == DISABLED
    assert DISABLED == (
        "Runtime Insights reads the runtime journal, which is disabled: set SHARPIT_RUNTIME_JOURNAL_ENABLED=true."
    )


def test_insights_report_golden_keys_23() -> None:
    journal = _journal()
    journal.offer(AI)
    report = InsightsService(journal).report()
    assert report["available"] is True
    assert list(report) == [
        "available", "unavailableReason", "window", "coverage", "checks", "observations", "limitations",
        "notExercised", "notExercisedOmitted",
    ]  # fmt: skip
    assert list(report["window"]) == [
        "runId", "firstEventAt", "lastEventAt", "retainedEvents", "requests", "evictedEvents", "droppedEvents",
    ]  # fmt: skip
    assert {tuple(row) for row in report["coverage"]} == {
        ("source", "events", "byRequestId", "byExecutionId", "byTraceId", "unlinked", "dropped")
    }
    assert len(report["checks"]) == 28
    assert {tuple(check) for check in report["checks"]} == {
        ("kind", "title", "status", "eligibleRequests", "findings", "reason")
    }
    finding = Finding("k", "s", True, "t", 1, 1, [], [], [], [], [])
    shown = InsightsService(journal, [FakeKind(evaluate=lambda _s: Evaluation(1, [finding]))]).report()
    assert list(shown["observations"][0]) == [
        "id", "kind", "subject", "status", "sentence", "eligible", "affected", "minimumTier", "whatToCheck",
        "exemplarRequestIds", "evidenceRows", "limitations", "listed", "unlistedReason",
    ]  # fmt: skip


def test_a_full_journal_is_projected_and_evaluated_well_within_the_read_budget() -> None:
    """Times projection and coverage over a full journal with stub kinds; not BootUI's budget test."""
    journal = _journal(max_events=50_000)
    for i in range(50_000):
        journal.offer_flat({"source": "ai", "operation": "chat", "inputTokens": i, "requestId": f"r{i % 700}"})
    service = InsightsService(journal)
    best = float("inf")
    for _ in range(3):
        start = time.perf_counter()
        report = service.report()
        best = min(best, time.perf_counter() - start)
    assert report["window"]["retainedEvents"] == 50_000
    check_wall_budget("insights report over a full journal", best, 2.0)


def test_the_window_counts_http_requests_only_when_http_is_produced(monkeypatch: pytest.MonkeyPatch) -> None:
    journal = _journal()
    journal.offer({"source": "http", "requestId": "r1"})
    assert InsightsService(journal).report()["window"]["requests"] == 0
    monkeypatch.setattr(snapshot_module, "PRODUCED_SOURCES", frozenset({"ai", "http"}))
    assert InsightsService(journal).report()["window"]["requests"] == 1


def test_the_window_spans_the_retained_events() -> None:
    journal = _journal()
    journal.offer(AI)
    journal.offer(AI)
    window = InsightsService(journal).report()["window"]
    assert window["retainedEvents"] == 2
    assert window["firstEventAt"] is not None
    assert window["lastEventAt"] >= window["firstEventAt"]


def test_a_kind_that_raises_is_unavailable_and_the_others_still_run() -> None:
    def boom(_snapshot: object) -> Evaluation:
        raise RuntimeError("secret detail")

    journal = _journal()
    journal.offer(AI)
    kinds = [FakeKind(kind="a", evaluate=boom), FakeKind(kind="b", evaluate=lambda _s: Evaluation(2, []))]
    report = InsightsService(journal, kinds).report()
    checks = report["checks"]
    assert "secret detail" not in json.dumps(report)
    a, b = checks[0], checks[1]
    assert (a["status"], a["reason"]) == ("UNAVAILABLE", "This observation could not be evaluated.")
    assert (b["status"], b["eligibleRequests"]) == ("EVALUATED", 2)


class _TearingJournal(RuntimeJournal):
    """A capture write lands right after each of the separate reads the old projection made."""

    def _tear(self) -> None:
        if not getattr(self, "torn", False):
            self.torn = True
            self.offer(AI)

    def status(self) -> dict[str, object]:
        status = super().status()
        self._tear()
        return status

    def records(self, source: str) -> tuple[dict[str, object], ...]:
        records = super().records(source)
        self._tear()
        return records


def test_the_snapshot_is_one_copy_so_the_window_equals_the_coverage() -> None:
    journal = _TearingJournal(sources=JOURNAL_SOURCES)
    journal.offer(AI)
    report = InsightsService(journal).report()
    assert report["window"]["retainedEvents"] == sum(row["events"] for row in report["coverage"])


def test_the_window_ends_at_the_newest_timestamp_not_the_last_event(monkeypatch: pytest.MonkeyPatch) -> None:
    stamps = iter([100_000_000, 90_000_000])  # time.time_ns() // 1_000_000 -> 100 then 90 (ns)
    monkeypatch.setattr("sharpit.engine.capture.journal.time.time_ns", lambda: next(stamps) * 1_000)
    journal = _journal()
    journal.offer(AI)
    journal.offer(AI)
    window = InsightsService(journal).report()["window"]
    assert window["firstEventAt"] == 100_000
    assert window["lastEventAt"] == 100_000


def _secret_finding() -> Finding:
    text = "leaked password=hunter2hunter2 here"
    return Finding("k", text, True, text, 1, 1, [], [], [], [], [text])


def test_finding_text_is_masked_in_the_report() -> None:
    kind = FakeKind(evaluate=lambda _s: Evaluation(1, [_secret_finding()], "uncounted password=hunter2hunter2"))
    journal = _journal()
    journal.offer(AI)
    report = InsightsService(journal, [kind]).report()
    assert "hunter2hunter2" not in json.dumps(report)


def test_a_kind_that_raises_logs_only_its_id(caplog: pytest.LogCaptureFixture) -> None:
    def boom(_snapshot: object) -> Evaluation:
        raise RuntimeError("secret detail")

    journal = _journal()
    journal.offer(AI)
    with caplog.at_level(logging.DEBUG, logger="sharpit"):
        InsightsService(journal, [FakeKind(kind="a-kind", evaluate=boom)]).report()
    assert "a-kind" in caplog.text
    assert "secret detail" not in caplog.text


def test_the_kind_spec_evaluate_is_typed_as_a_callable() -> None:
    annotation = KindSpec.evaluate.fget.__annotations__["return"]  # type: ignore[union-attr]
    assert annotation == "Callable[[Snapshot], Evaluation] | None"
