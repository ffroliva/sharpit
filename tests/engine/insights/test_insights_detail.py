"""Runtime Insights I2: one observation's detail, and its text under METADATA_ONLY and secret masking."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights.agent_view import UNDER_DEFAULT_FLOOR
from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.service import InsightsService, id_of
from sharpit.engine.masking import Exposure, Masker
from sharpit.settings_registry import JOURNAL_SOURCES

AI = {"source": "ai", "operation": "chat", "inputTokens": 5, "outputTokens": 7}
UNKNOWN = "No observation {} in this run's retained events: it may have been evicted or cleared."
UNCOUNTED_WITHHELD = "Some recorded work was not counted; the detail is withheld under METADATA_ONLY exposure."
OMITTED = "The text of this observation is withheld under METADATA_ONLY exposure: counts, ids and statuses only."
APP_EVENT = "The runtime journal does not record the app-event source (SHARPIT_RUNTIME_JOURNAL_SOURCES)."


def _finding(**kwargs: object) -> Finding:
    fields: dict[str, object] = {
        "key": "GET /x", "subject": "GET /x", "sufficient": True, "sentence": "repeated a SELECT 3 times",
        "eligible": 4, "affected": 3, "what_to_check": ["Check the call site."], "exemplar_request_ids": ["r-1"],
        "columns": ["call site", "count"], "rows": [[f"a.py:{i}", str(i)] for i in range(25)], "limitations": [],
    }  # fmt: skip
    return Finding(**{**fields, **kwargs})  # type: ignore[arg-type]


@dataclass(frozen=True)
class FakeKind:
    kind: str = "uncounted-work"
    title: str = "Uncounted work"
    minimum_tier: str = "REQUEST_ID"
    reads: frozenset[str] = frozenset({"ai"})
    optional_reads: frozenset[str] = frozenset()
    evaluate: object = field(default=lambda _snapshot: Evaluation(1, [_finding()]))


def _service(exposure: Exposure = Exposure.MASKED, finding: Finding | None = None) -> InsightsService:
    journal = RuntimeJournal(sources=JOURNAL_SOURCES, masker=Masker(exposure, True))
    journal.offer(AI)
    found = finding or _finding()
    return InsightsService(journal, [FakeKind(evaluate=lambda _s: Evaluation(1, [found]))])


def _check(kind: str) -> dict[str, object]:
    journal = RuntimeJournal(sources=JOURNAL_SOURCES)
    journal.offer(AI)
    return next(c for c in InsightsService(journal).report()["checks"] if c["kind"] == kind)


def test_insight_unknown_id_answers_bootui_not_found() -> None:
    detail = _service().insight("conformance-unknown:0000000000")
    assert detail == {
        "available": False, "unavailableReason": UNKNOWN.format("conformance-unknown:0000000000"),
        "observation": None, "columns": [], "rows": [], "truncated": 0,
    }  # fmt: skip


def test_insight_of_a_disabled_journal_is_unavailable_with_the_report_reason() -> None:
    detail = InsightsService(None).insight("x:1")
    assert detail["available"] is False
    assert "SHARPIT_RUNTIME_JOURNAL_ENABLED" in str(detail["unavailableReason"])


def test_insight_returns_the_observation_with_at_most_20_evidence_rows() -> None:
    service = _service()
    observation = service.report()["observations"][0]
    detail = service.insight(str(observation["id"]))
    assert list(detail) == ["available", "unavailableReason", "observation", "columns", "rows", "truncated"]
    assert detail["available"] is True
    assert detail["observation"] == observation
    assert detail["columns"] == ["call site", "count"]
    assert len(detail["rows"]) == 20  # type: ignore[arg-type]
    assert detail["rows"][0] == {"cells": ["a.py:0", "0"]}  # type: ignore[index]
    assert detail["truncated"] == 5


def test_insight_id_is_the_kind_and_the_stable_hash_of_the_key() -> None:
    assert _service().report()["observations"][0]["id"] == id_of("uncounted-work", "GET /x")


def test_metadata_only_marks_withheld_text_with_a_limitation_and_keeps_counts_and_ids() -> None:
    row = _service(Exposure.METADATA_ONLY).report()["observations"][0]
    assert (row["subject"], row["sentence"]) == ("", "")
    assert row["whatToCheck"] == []
    assert row["exemplarRequestIds"] == ["r-1"]
    assert (row["eligible"], row["affected"], row["evidenceRows"]) == (4, 3, 20)
    assert OMITTED in row["limitations"]  # type: ignore[operator]


def test_metadata_only_withholds_evidence_cells_and_says_how_many_rows_it_left_out() -> None:
    service = _service(Exposure.METADATA_ONLY)
    detail = service.insight(str(service.report()["observations"][0]["id"]))
    assert detail["rows"] == []
    assert detail["truncated"] == 25
    assert detail["columns"] == ["call site", "count"]


def test_masked_exposure_does_not_mark_the_text_as_withheld() -> None:
    row = _service().report()["observations"][0]
    assert row["sentence"] == "repeated a SELECT 3 times"
    assert OMITTED not in row["limitations"]  # type: ignore[operator]


def test_what_to_check_exemplar_ids_and_evidence_cells_are_masked() -> None:
    finding = _finding(
        what_to_check=["Retry with password=hunter2 set."], exemplar_request_ids=["r-1 password=hunter2"],
        rows=[["call password=hunter2", "1"]],
    )  # fmt: skip
    service = _service(finding=finding)
    report = service.report()
    detail = service.insight(str(report["observations"][0]["id"]))
    assert "hunter2" not in json.dumps([report, detail])


@pytest.mark.parametrize("kind", ["proxy-bypass", "transactional-listener-skipped"])
def test_proxy_bypass_never_applicable_pending_owner(kind: str) -> None:
    check = _check(kind)
    assert check["status"] == "NOT_APPLICABLE"
    assert "No eligible work" not in str(check["reason"])


def test_after_commit_writes_not_applicable_without_app_event() -> None:
    check = _check("after-commit-writes")
    assert check["status"] == "NOT_APPLICABLE"
    assert check["reason"] == APP_EVENT


def test_a_masker_returning_the_empty_string_never_lets_a_raw_exemplar_id_through() -> None:
    service = _service()
    service._mask = lambda _text: ""  # type: ignore[method-assign]  # a fake masker that blanks everything
    row = service.report()["observations"][0]
    assert row["exemplarRequestIds"] == [""]


def test_metadata_only_still_carries_the_under_floor_decision() -> None:
    finding = _finding(limitations=[UNDER_DEFAULT_FLOOR])
    row = _service(Exposure.METADATA_ONLY, finding).report()["observations"][0]
    assert UNDER_DEFAULT_FLOOR in row["limitations"]  # type: ignore[operator]


def test_metadata_only_keeps_a_check_with_uncounted_work_from_reading_clean() -> None:
    # the kind's uncounted sentence is masked away under METADATA_ONLY; the check must still say work went uncounted
    journal = RuntimeJournal(sources=JOURNAL_SOURCES, masker=Masker(Exposure.METADATA_ONLY, True))
    journal.offer(AI)
    kind = FakeKind(evaluate=lambda _s: Evaluation(1, [], "3 AI operations joined no retained request."))
    check = InsightsService(journal, [kind]).report()["checks"][0]
    assert check["reason"] == UNCOUNTED_WITHHELD
