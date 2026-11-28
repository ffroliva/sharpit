"""No journal-reading output shows a security-sinks record: its hashes stay in the journal."""

from __future__ import annotations

import json

from sharpit.engine.capture.activity import journal_status_dto
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights.snapshot import project
from sharpit.settings_registry import JOURNAL_SOURCES

CANARY = 7_340_192_837_465


def _journal() -> RuntimeJournal:
    journal = RuntimeJournal(sources=JOURNAL_SOURCES)
    offered = journal.offer(
        {
            "source": "security-sinks",
            "kind": "file-path",
            "target": "./{file}",
            "parameter": "file",
            "callSite": "app.handler",
            "at": 1,
            "requestId": "a" * 16,
            "rawHash": CANARY,
            "redactedHash": CANARY + 1,
        }
    )
    assert offered
    return journal


def test_the_journal_status_never_shows_a_sink_hash() -> None:
    journal = _journal()
    assert str(CANARY) not in json.dumps([journal.status(), journal_status_dto(journal)])


def test_the_insights_snapshot_never_reads_sink_records() -> None:
    snapshot = project(_journal())
    assert str(CANARY) not in json.dumps([snapshot.status, snapshot.records], default=str)
