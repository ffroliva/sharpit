"""Runtime Insights I2: the Profile resources floor (BootUI ``ResourceProfileService``): nothing is ever started."""

from __future__ import annotations

import threading

import pytest

from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights.profile import NO_SAMPLER, RESOURCES_OFF, ResourceProfile
from sharpit.engine.collectors.insights.service import DISABLED
from sharpit.settings_registry import JOURNAL_SOURCES

KEYS = [
    "state", "reason", "sampler", "startedAt", "endsAt", "finishedAt", "maxDurationSeconds", "cpuSamples",
    "outsideSamples", "requests", "routes", "routesOmitted", "limitations",
]  # fmt: skip


# ported: ResourceProfileServiceTests.withoutTheResourcesSourceOrTheJournalNoSessionStarts
def test_without_the_resources_source_or_the_journal_no_session_starts() -> None:
    without = RuntimeJournal(sources=("http", "sql"))
    refused = ResourceProfile(without, 5).start()
    assert refused["state"] == "UNAVAILABLE"
    assert refused["reason"] == RESOURCES_OFF
    disabled = ResourceProfile(None, 5).status()
    assert disabled["state"] == "UNAVAILABLE"
    assert disabled["reason"] == DISABLED


def test_the_off_reason_names_the_sharpit_setting() -> None:
    assert RESOURCES_OFF == (
        "Profile resources joins samples to the request segments the runtime journal's resources source measures: "
        "add resources to SHARPIT_RUNTIME_JOURNAL_SOURCES."
    )


def test_the_no_sampler_reason_says_sharpit_has_none() -> None:
    assert NO_SAMPLER == "sharpit has no resource sampler."


@pytest.mark.parametrize("call", ["status", "start", "stop"])
def test_resource_profile_floor_starts_nothing(call: str) -> None:
    threads = threading.active_count()
    shown = getattr(ResourceProfile(RuntimeJournal(sources=JOURNAL_SOURCES), 45.0), call)()
    assert list(shown) == KEYS
    assert shown["state"] == "UNAVAILABLE"
    assert shown["reason"] == NO_SAMPLER
    assert shown["maxDurationSeconds"] == 45
    assert (shown["cpuSamples"], shown["outsideSamples"], shown["requests"]) == (0, 0, 0)
    assert (shown["routes"], shown["routesOmitted"], shown["limitations"]) == ([], 0, [])
    assert threading.active_count() == threads
