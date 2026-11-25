"""The two anonymous-access kinds are not applicable to FastAPI, whatever the journal holds."""

from __future__ import annotations

import pytest

from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights.service import InsightsService
from sharpit.settings_registry import JOURNAL_SOURCES

ANONYMOUS_KINDS = ("anonymous-data-reach", "anonymous-success-on-restricted-route")


def _checks(journal: RuntimeJournal) -> dict[str, dict[str, object]]:
    return {check["kind"]: check for check in InsightsService(journal).report()["checks"]}


@pytest.mark.parametrize("sources", [JOURNAL_SOURCES, ("http",)], ids=["every-source", "http-only"])
@pytest.mark.parametrize("kind", ANONYMOUS_KINDS)
def test_anonymous_access_kinds_say_why_they_cannot_apply(kind: str, sources: object) -> None:
    check = _checks(RuntimeJournal(sources=sources))[kind]  # type: ignore[arg-type]
    assert check["status"] == "NOT_APPLICABLE"
    assert "makes no authorization decision" in str(check["reason"])


@pytest.mark.parametrize("kind", ANONYMOUS_KINDS)
def test_anonymous_access_kinds_point_to_the_partial_static_check(kind: str) -> None:
    reason = str(_checks(RuntimeJournal(sources=JOURNAL_SOURCES))[kind]["reason"])  # type: ignore[arg-type]
    assert "SEC-AUTHZ-001" in reason
    assert "state-changing routes" in reason
