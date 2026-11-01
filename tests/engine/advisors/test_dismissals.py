"""DismissalStore (port of BootUI ``DismissedRulesStore`` and ``DismissedRulesStoreTests``).

Ported ids are rewritten into sharpit's vulnerability rule-id form (``<vulnId>::pypi:<name>``); REST API ids
(``RAPI-...``) are accepted too (spec §8: charset ``[A-Za-z0-9._:-]{1,200}`` and an owning panel). Dropped:
``roundTripsRuleIdsContainingSlashesAndSpaces`` (sharpit rejects such ids, see ``test_dismiss_rejects_bad_ids`` and
``test_rapi_id_accepted_quote_space_slash_refused``).
"""

from pathlib import Path
from typing import Any

import pytest

from sharpit.engine.advisors.dismissals import FILE_NAME, NO_PANEL_MESSAGE, DismissalStore, owning_panel
from sharpit.engine.advisors.report import apply_dismissals, severity_counts
from sharpit.engine.advisors.rules import SEVERITIES
from sharpit.engine.paging import BadRequest

A = "GHSA-aaaa-bbbb-cccc::pypi:jinja2"
B = "PYSEC-2017-9999::pypi:jinja2"
C = "CVE-2024-1::pypi:flask"


# ported: DismissedRulesStoreTests.loadReturnsEmptySetWhenFileDoesNotExist
def test_list_empty_when_file_missing(tmp_path: Path):
    assert DismissalStore(tmp_path).list() == []


# ported: DismissedRulesStoreTests.dismissPersistsRuleIdsAndIsIdempotent
def test_add_persists_and_is_idempotent(tmp_path: Path):
    store = DismissalStore(tmp_path)
    assert store.add(A) == [A]
    assert store.add(B) == [A, B]
    assert store.add(A) == [A, B]
    assert DismissalStore(tmp_path).list() == [A, B]


# ported: DismissedRulesStoreTests.restoreRemovesRuleIdsAndIsANoOpForUnknownRules
def test_remove_and_unknown_is_noop(tmp_path: Path):
    store = DismissalStore(tmp_path)
    store.add(A)
    store.add(B)
    assert store.remove(A) == [B]
    assert store.remove(C) == [B]
    assert DismissalStore(tmp_path).list() == [B]


# ported: DismissedRulesStoreTests.persistedFileUsesAGenericBootUiYamlNode
def test_file_format(tmp_path: Path):
    store = DismissalStore(tmp_path)
    store.add(A)
    store.add(C)
    assert (tmp_path / FILE_NAME).read_bytes() == (
        f"# sharpit configuration (developer-local; safe to delete).\n\ndismissedRules:\n  - {A}\n  - {C}\n"
    ).encode()


# ported: DismissedRulesStoreTests.repeatedWritesAreByteStable
def test_repeated_writes_byte_stable(tmp_path: Path):
    store = DismissalStore(tmp_path)
    store.add(A)
    store.add(C)
    first = (tmp_path / FILE_NAME).read_bytes()
    store.add(B)
    store.remove(B)
    assert (tmp_path / FILE_NAME).read_bytes() == first


# ported: DismissedRulesStoreTests.preservesOtherTopLevelSectionsAcrossWrites
def test_dismissal_file_preserves_other_lines(tmp_path: Path):
    file = tmp_path / FILE_NAME
    file.write_text(f"# My sharpit config\nsomeSetting: value\nnested:\n  key: 1\ndismissedRules:\n  - {A}\n")
    DismissalStore(tmp_path).add(B)
    written = file.read_text()
    assert "# My sharpit config" in written
    assert "someSetting: value" in written
    assert "nested:\n  key: 1" in written
    assert written.count("dismissedRules:") == 1
    assert DismissalStore(tmp_path).list() == [A, B]


# ported: DismissedRulesStoreTests.rewritesAnInlineEmptyNodeToBlockForm
def test_inline_empty_node_rewritten_to_block(tmp_path: Path):
    file = tmp_path / FILE_NAME
    file.write_text("dismissedRules: []\n")
    store = DismissalStore(tmp_path)
    assert store.list() == []
    store.add(A)
    assert file.read_text().count("dismissedRules") == 1
    assert DismissalStore(tmp_path).list() == [A]


# ported: DismissedRulesStoreTests.createsTheParentDirectoryOnFirstWrite
def test_dismiss_restore_roundtrip_file_created_lazily(tmp_path: Path):
    state = tmp_path / "nested" / ".sharpit"
    store = DismissalStore(state)
    assert store.list() == []
    assert store.remove(A) == []
    assert not state.exists()  # nothing is written until the first add
    assert store.add(A) == [A]
    assert (state / FILE_NAME).is_file()
    assert store.remove(A) == []
    assert DismissalStore(state).list() == []
    assert [p.name for p in state.iterdir()] == [FILE_NAME]  # no temp file left behind


@pytest.mark.parametrize(
    "rule_id",
    [
        'GHSA-1"::pypi:jinja2',
        "GHSA-1\n::pypi:jinja2",
        "GHSA-1::pypi:jinja2\n  - injected",
        "GHSA-1\\x::pypi:jinja2",
        "GHSA-1::jinja2",
        "GHSA-1::pypi:Jinja2",
        "::pypi:jinja2",
        "GHSA-1::pypi:",
        "",
    ],
)
def test_dismiss_rejects_bad_ids(tmp_path: Path, rule_id: str):
    store = DismissalStore(tmp_path)
    store.add(A)
    before = (tmp_path / FILE_NAME).read_bytes()
    with pytest.raises(BadRequest):
        store.add(rule_id)
    with pytest.raises(BadRequest):
        store.remove(rule_id)
    assert (tmp_path / FILE_NAME).read_bytes() == before


def test_list_reads_the_file_once_until_it_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Task P1: report() lists dismissals on every poll; the file is re-read only when a write or an edit changes it
    store = DismissalStore(tmp_path)
    store.add(A)
    reads: list[int] = []
    real = Path.read_text

    def counting(self: Path, *args: object, **kwargs: object) -> str:
        reads.append(1)
        return real(self, *args, **kwargs)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(Path, "read_text", counting)
    assert store.list() == [A]
    assert store.list() == [A]
    assert len(reads) <= 1
    store.add(B)
    assert store.list() == [A, B]
    target = tmp_path / FILE_NAME
    target.write_text(target.read_text(encoding="utf-8") + f"  - {C}\n", encoding="utf-8")  # an edit by hand
    assert store.list() == [A, B, C]


def test_rapi_id_accepted_quote_space_slash_refused(tmp_path: Path):
    store = DismissalStore(tmp_path)
    assert store.add("RAPI-MAP-001") == ["RAPI-MAP-001"]
    assert store.add(A) == ["RAPI-MAP-001", A]
    assert DismissalStore(tmp_path).list() == ["RAPI-MAP-001", A]
    before = (tmp_path / FILE_NAME).read_bytes()
    unregistered = ("RAPI-MAP-004", "RAPI-" + "1" * 195)  # T10: only registered REST API rule ids have an owner
    for bad in ['RAPI-"1', "RAPI-MAP 001", "RAPI-MAP/001", "RAPI-\\1", "RAPI-1\n  - x", "RAPI-", "RAPI-" + "1" * 196,
                *unregistered]:  # fmt: skip
        with pytest.raises(BadRequest):
            store.add(bad)
        with pytest.raises(BadRequest):
            store.remove(bad)
    assert (tmp_path / FILE_NAME).read_bytes() == before
    longest = "V-" + "1" * 188 + "::pypi:abc"  # 200 characters is the longest id
    assert len(longest) == 200
    assert store.add(longest)[-1] == longest
    with pytest.raises(BadRequest):
        store.add("V-" + "1" * 189 + "::pypi:abc")


@pytest.mark.parametrize(
    ("rule_id", "panel"),
    [
        ("RAPI-MAP-001", "rest-api"),
        ("RAPI-DOC-002", "rest-api"),
        ("RAPI-MAP-004", None),  # documented by BootUI, not ported (T10)
        ("RAPI-NOPE-1", None),
        (A, "vulnerabilities"),
        ("PYSEC-2017-9999::pypi:zope.interface", "vulnerabilities"),
        ("SPRING-WEB-001", None),
        ("rapi-map-001", None),
        ("GHSA-1::pypi:Jinja2", None),
        ("::pypi:jinja2", None),
        ("GHSA-1::jinja2", None),
        ("", None),
    ],
)
def test_owning_panel(rule_id: str, panel: str | None):
    assert owning_panel(rule_id) == panel


def test_unknown_owner_refused_before_the_file_is_touched(tmp_path: Path):
    store = DismissalStore(tmp_path)
    with pytest.raises(BadRequest):
        store.add("SPRING-WEB-001")
    assert list(tmp_path.iterdir()) == []


FP = "rest-api:RAPI-MAP-001:0123456789abcdef"
RUNTIME_FP = "test-runtime:sharpit.n-plus-one:0123456789abcdef"


def test_fingerprint_dismissal_round_trip(tmp_path: Path):
    store = DismissalStore(tmp_path)
    assert store.add(FP) == [FP]
    assert "dismissedRules:\n  - " + FP in (tmp_path / FILE_NAME).read_text(encoding="utf-8")
    assert DismissalStore(tmp_path).list() == [FP]
    assert store.remove(FP) == []


def test_owning_panel_for_fingerprints():
    assert owning_panel(FP) == "rest-api"
    assert owning_panel("vulnerabilities:GHSA-1::pypi:jinja2:0123456789abcdef") is None  # nothing builds these
    assert owning_panel(RUNTIME_FP) is None


def test_test_runtime_fingerprint_refused_with_no_panel_message(tmp_path: Path):
    store = DismissalStore(tmp_path)
    with pytest.raises(BadRequest) as raised:
        store.add(RUNTIME_FP)
    assert str(raised.value) == NO_PANEL_MESSAGE.format(advisor="test-runtime")
    assert list(tmp_path.iterdir()) == []


def _occurrence_report() -> dict[str, Any]:
    result = {
        "id": "RAPI-004",
        "severity": "HIGH",
        "status": "FAILED",
        "violationCount": 3,
        "sampleViolations": ["one", "two", "three"],
        "dismissed": False,
    }
    return {
        "violationsFound": 1,
        "severityCounts": severity_counts([("HIGH", 3)], SEVERITIES),
        "scan": {"violationsFound": 1},
        "results": [result],
    }


_OCCURRENCES = {
    "RAPI-004": [("rest-api:RAPI-004:a", "one"), ("rest-api:RAPI-004:b", "two"), ("rest-api:RAPI-004:c", "three")]
}


def test_apply_dismissals_per_occurrence():
    out = apply_dismissals(_occurrence_report(), {"rest-api:RAPI-004:a", "rest-api:RAPI-004:b"}, _OCCURRENCES)
    result = out["results"][0]
    assert result["violationCount"] == 1
    assert result["sampleViolations"] == ["three"]
    assert result["dismissed"] is False
    assert {c["severity"]: c["count"] for c in out["severityCounts"]}["HIGH"] == 1
    assert out["violationsFound"] == 1


def test_all_occurrences_dismissed_keeps_rule_restorable():
    # a rule is `dismissed` only when its own id is dismissed: Restore DELETEs that id, which fingerprints never stored
    out = apply_dismissals(_occurrence_report(), {fp for fp, _ in _OCCURRENCES["RAPI-004"]}, _OCCURRENCES)
    result = out["results"][0]
    assert result["dismissed"] is False
    assert result["violationCount"] == 0
    assert result["sampleViolations"] == []
    assert result["status"] == "PASSED"
    assert out["violationsFound"] == 0
    assert {c["severity"]: c["count"] for c in out["severityCounts"]}["HIGH"] == 0


def test_apply_dismissals_without_occurrences_ignores_fingerprints():
    out = apply_dismissals(_occurrence_report(), {"rest-api:RAPI-004:a"})
    assert out["results"][0]["violationCount"] == 3


def test_partial_dismissal_refills_samples_beyond_the_first_ten():
    texts = [f"occurrence {i}" for i in range(12)]
    fingerprints = [f"rest-api:RAPI-004:{i:016x}" for i in range(12)]
    report = _occurrence_report()
    report["results"][0].update(violationCount=12, sampleViolations=texts[:10])
    out = apply_dismissals(report, set(fingerprints[:10]), {"RAPI-004": list(zip(fingerprints, texts, strict=True))})
    result = out["results"][0]
    assert result["violationCount"] == 2
    assert result["sampleViolations"] == texts[10:]
