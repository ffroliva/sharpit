"""Spec A5: no output of one job is an input to another, so the scan only ever reads raw text.

A static test cannot follow a string, so this one is dynamic: it wraps the lexer's entry (``sqlscan._read``, which every
scan goes through) in a spy, drives every surface of ``test_statement_surfaces.SURFACES`` over the corpus, and asserts
each text the lexer read is a substring of the raw value handed to the surface. The one named exception is the
ambiguity check's read of the text with its backslashes removed (spec §3, r4). Two groupings that read stored rows,
``activity._groups`` and ``sqlinsights._add``, are driven the same way, with capture on and off.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from unittest import mock

import pytest
from tests.masking import test_statement_surfaces as gates
from tests.masking.sql_corpus import Row

from sharpit.engine import sqltext
from sharpit.engine.capture import activity, sqlinsights, sqlscan
from sharpit.engine.capture.sqlscan import normalize
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import lexer

pytestmark = pytest.mark.timeout(max(300, gates.ROWS // 5))
ACTIVITY_THRESHOLD = 3


def _activity_groups(dialect: gates.Dialect, masker: Masker, statement: str) -> str | None:
    row = gates._recorded(masker, statement, dialect)  # pyright: ignore[reportPrivateUsage]
    groups = activity._groups([row], ACTIVITY_THRESHOLD)  # pyright: ignore[reportPrivateUsage]
    return groups[0]["sql"] if groups else None


def _insights_group(dialect: gates.Dialect, masker: Masker, statement: str) -> str | None:
    groups: dict[str, sqlinsights.Group] = {}
    sqlinsights._add(groups, gates._recorded(masker, statement, dialect))  # pyright: ignore[reportPrivateUsage]
    return next(iter(groups.values())).sql if groups else None


def _grouping_surfaces() -> dict[str, gates.Surface]:
    surfaces: dict[str, gates.Surface] = {}
    for mode, dialect, _ in gates.MODES:
        for name, grouping in (("activity_groups", _activity_groups), ("sql_insights", _insights_group)):
            for capture, flag in (("on", True), ("off", False)):
                masker = Masker(Exposure.MASKED, flag)
                surfaces[f"{name}_capture_{capture}-{mode}"] = (
                    lambda _masker, statement, g=grouping, m=masker, d=dialect: g(d, m, statement)  # noqa: B008
                )
    return surfaces


GROUPING_SURFACES = _grouping_surfaces()
ALL_SURFACES: dict[str, gates.Surface] = {**gates.SURFACES, **GROUPING_SURFACES}


def _is_raw(text: str, raw: str) -> bool:
    """Raw text, or one of two named reads: the ambiguity check's text without its backslashes (spec §3, r4), and the
    bracket check's sentinel (``_two_way_bracket_end``: a slice of the raw text closed with a ``]`` of its own)."""
    bracket = text.endswith("]") and "[" + text[:-1] in raw  # the body after a ``[`` of the raw text, plus the sentinel
    return text in raw or text in raw.replace("\\", "") or bracket


def lexer_reads_off_raw(
    surface: gates.Surface, rows: Sequence[Row], extra_raw: Callable[[Row], Sequence[str]] | None = None
) -> tuple[list[tuple[Row, str]], int]:
    """The (row, text) pairs the lexer read that are not in the row's raw value, and how many reads it saw."""
    read = lexer._read  # pyright: ignore[reportPrivateUsage]
    seen: list[str] = []

    def spy(source: str, rules: object) -> object:
        seen.append(source)
        return read(source, rules)  # type: ignore[arg-type]

    off: list[tuple[Row, str]] = []
    total = 0
    with mock.patch.object(lexer, "_read", spy):
        for row in rows:
            sqlscan._normalized.cache_clear()  # pyright: ignore[reportPrivateUsage]
            seen.clear()
            surface(gates._MASKER, row.text)  # pyright: ignore[reportPrivateUsage]
            allowed = (row.text, *(extra_raw(row) if extra_raw else ()))
            off += [(row, text) for text in seen if not any(_is_raw(text, raw) for raw in allowed)]
            total += len(seen)
    sqlscan._normalized.cache_clear()  # pyright: ignore[reportPrivateUsage]
    return off, total


def _names(names: Sequence[str]) -> list[object]:
    return gates._params(names)  # pyright: ignore[reportPrivateUsage]


ZERO_READS = {
    "log_handler_statement-unsupported": "unsupported statements are hidden before scanning",
    "mysql_last_error-mysql": "the applier's message has no [SQL: block to parse back, so mask_text never scans",
    "test_session_exception-mysql": "the test-session exception has no SQL statement to scan",
    **{name: "unsupported SQL is hidden before scanning" for name in ALL_SURFACES if name.endswith("-unsupported")},
}


def assert_reads_raw(
    name: str, surface: gates.Surface, rows: Sequence[Row], zero_reads: Sequence[str] = tuple(ZERO_READS)
) -> None:
    """The one assertion of the gate: every read is raw text, and a surface makes reads unless it is named in
    ``zero_reads`` (and then it must make none, so a stale entry fails)."""

    def raw_inputs(row: Row) -> tuple[str, ...]:
        inputs = []
        if name in gates.ERROR_SURFACES:
            carrier = gates.ERROR_SURFACES[name][1]
            inputs.append(gates.error_text(row.text, carrier))
        if name.startswith("recorder_error_of_another_statement-"):
            inputs.append("SELECT 2")
        return tuple(inputs)

    off, total = lexer_reads_off_raw(surface, rows, raw_inputs)
    assert not off, f"{len(off)} reads; first, of {off[0][1][:120]!r} for raw {off[0][0].text[:120]!r}" if off else ""
    if name in zero_reads:
        assert total == 0, f"{name} is allowed zero reads but made {total}; drop it from ZERO_READS"
    else:
        assert total > 0, f"{name} made no lexer reads: it scans nothing, or is missing from ZERO_READS"


@pytest.mark.parametrize("name", _names(list(ALL_SURFACES)))
def test_the_scan_only_reads_raw_text(name: str) -> None:
    assert_reads_raw(name, ALL_SURFACES[name], gates.gate_rows(gates._mode(name)))  # pyright: ignore[reportPrivateUsage]


def test_the_zero_read_allowlist_names_real_surfaces() -> None:
    assert set(ZERO_READS) <= set(ALL_SURFACES)


def _normalised_twice(_masker: object, statement: str) -> str:
    first = normalize(statement, gates.Dialect.MYSQL_FAMILY)
    return normalize(first.sql, gates.Dialect.MYSQL_FAMILY).sql


def test_a_planted_second_normalisation_fails_the_gate() -> None:
    with pytest.raises(AssertionError, match="reads; first"):
        assert_reads_raw("planted", _normalised_twice, gates.gate_rows("mysql")[:200])  # type: ignore[arg-type]


def test_a_planted_surface_that_scans_nothing_fails_the_gate() -> None:
    with pytest.raises(AssertionError, match="made no lexer reads"):
        assert_reads_raw("planted", lambda _masker, statement: statement, gates.gate_rows("mysql")[:50])


def test_a_stale_zero_read_entry_fails_the_gate() -> None:
    with pytest.raises(AssertionError, match="drop it from ZERO_READS"):
        assert_reads_raw(
            "recorder_sql-mysql",
            ALL_SURFACES["recorder_sql-mysql"],
            gates.gate_rows("mysql")[:50],
            ["recorder_sql-mysql"],
        )


def test_the_spy_sees_the_scan_of_a_surface() -> None:
    _, total = lexer_reads_off_raw(ALL_SURFACES["recorder_sql-mysql"], gates.gate_rows("mysql")[:50])
    assert total > 0


def test_the_backslash_read_is_allowed_by_name_only() -> None:
    """The exception is the text with its backslashes removed; a text changed any other way still fails."""
    rows = [row for row in gates.gate_rows("mysql") if "\\" in row.text][:50]
    assert rows
    off, _ = lexer_reads_off_raw(
        lambda _masker, statement: normalize(statement.upper(), gates.Dialect.MYSQL_FAMILY).sql, rows
    )
    assert off


@pytest.mark.parametrize("capture", [True, False])
def test_a_recorded_row_carries_its_shape(capture: bool) -> None:
    row = gates._recorded(Masker(Exposure.MASKED, capture), "SELECT 'x'", gates.Dialect.MYSQL_FAMILY)  # pyright: ignore[reportPrivateUsage]
    assert row["shape"] == sqltext.statement_shape(
        Masker(Exposure.MASKED, capture), "SELECT 'x'", gates.Dialect.MYSQL_FAMILY
    )


def _row_with_other_text() -> dict[str, object]:
    """A recorded row whose stored text is not what its recorded shape says: only the shape may decide the group."""
    row = gates._recorded(Masker(Exposure.MASKED, True), "SELECT 'x' FROM t", gates.Dialect.MYSQL_FAMILY)  # pyright: ignore[reportPrivateUsage]
    return {**row, "sql": "stored text that is not the statement"}


def test_sql_insights_groups_by_the_recorded_shape() -> None:
    groups: dict[str, sqlinsights.Group] = {}
    sqlinsights._add(groups, _row_with_other_text())  # pyright: ignore[reportPrivateUsage,reportArgumentType]
    assert [g.sql for g in groups.values()] == ["SELECT ? FROM t"]


def test_activity_groups_by_the_recorded_shape() -> None:
    groups = activity._groups([_row_with_other_text()], ACTIVITY_THRESHOLD)  # pyright: ignore[reportPrivateUsage,reportArgumentType]
    assert [g["sql"] for g in groups] == ["SELECT ? FROM t"]
