"""DismissalStore (port of BootUI ``DismissedRulesStore`` and ``DismissedRulesStoreTests``).

Ported ids are rewritten into sharpit's vulnerability rule-id form (``<vulnId>::pypi:<name>``), since the store only
accepts those. Dropped: ``roundTripsRuleIdsContainingSlashesAndSpaces`` (sharpit rejects such ids, see
``test_dismiss_rejects_bad_ids``).
"""

from pathlib import Path

import pytest

from sharpit.engine.collectors.vulns.dismissals import FILE_NAME, DismissalStore
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
