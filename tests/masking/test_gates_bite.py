"""The masking gates can fail: planted builds and lexer mutants (spec A1, A3, revision 3; AGENTS.md retrospective).

A gate counts only after leaking and blanking builds both fail it. Revision 2's corpus let 11 lexer branches be deleted
without a failure, and an earlier generator scored 0 on builds leaking 17,000 of 30,000 statements.

* Planted builds: a surface that leaks, blanks or over-cuts must fail its gate on more rows than the real build does.
* Mutants: one source edit per lexer branch, applied to a scratch copy of ``src`` and run in a subprocess, never to
  the repo's files. A mutant is killed when it raises the gate's failing-row count above the unmutated build's, on the
  same rows. The gate is already red on head, so "turns it red" would prove nothing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import pytest
from tests.masking import mutant_worker, sql_corpus
from tests.masking import test_statement_surfaces as gates

from sharpit.engine.capture import sqltrace
from sharpit.engine.masking import Masker

ROOT = Path(__file__).resolve().parents[2]
ROWS = 300  # a few hundred rows keep each mutant to seconds; the reds at 60,000 rows are Task 11's
SEEDS = (7,)
pytestmark = pytest.mark.timeout(120)


class SurvivedMutant(AssertionError):
    """The gate failed no more rows with the mutation than without it."""


# --- planted builds --------------------------------------------------------------------------------------------------


def _leak(_masker: Masker, text: str) -> str:
    return text


def _blank(_masker: Masker, _text: str) -> str:
    return "?"


def _overcut(_masker: Masker, text: str) -> str:
    return text.split("'", 1)[0].strip() + " ?"


SURFACE = "db_statement-generic"
BASE_ROWS = sql_corpus.rows(7, ROWS)


@pytest.mark.parametrize(
    ("build", "gate"),
    [(_leak, "visible"), (_blank, "shape"), (_overcut, "shape")],
    ids=["leak-visible", "blank-shape", "overcut-shape"],
)
def test_a_planted_build_fails_each_gate(build: gates.Surface, gate: str) -> None:
    gate_of = {"visible": gates.failures_visible, "shape": gates.failures_shape}[gate]
    planted = len(gate_of(build, BASE_ROWS))
    real = len(gate_of(gates.SURFACES[SURFACE], BASE_ROWS))
    assert planted > real, f"{gate}: planted {planted} rows, the real build {real}"


def _ideal_error(carrier: gates.Carrier) -> gates.Surface:
    """An error that reads back: the corpus's own ``expected`` in the block, parameters hidden, driver and link kept."""
    shapes = {row.text: row.expected for row in BASE_ROWS}

    def ideal(_masker: Masker, statement: str) -> str:
        return (
            f"{carrier.shown}\n[SQL: {shapes[statement]}]\n[parameters: {gates.MASK}]\n"
            f"(Background on this error at: {carrier.link})"
        )

    return ideal


def test_the_regions_gate_passes_an_ideal_error_and_fails_a_blank_one() -> None:
    """Head fails every row's regions (its parameters show), so the ceiling is shown against an ideal build."""
    _, carrier = gates.ERROR_SURFACES["recorder_error-generic"]
    ideal = gates.failures_regions(_ideal_error(carrier), BASE_ROWS, carrier)
    planted = gates.failures_regions(_blank, BASE_ROWS, carrier)
    assert not ideal, f"{len(ideal)} rows fail an ideal error: the oracle is wrong"
    assert len(planted) == sum(gates._closes(row) for row in BASE_ROWS)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


# --- mutants ---------------------------------------------------------------------------------------------------------


class Mutant(NamedTuple):
    anchor: str  # a source snippet that must occur exactly once in the scanner
    replacement: str
    surface: str  # the surface the mutant is driven through
    gate: str  # the gate it must raise: ``visible`` (a literal shown) or ``shape`` (the statement lost its shape)


KEEP = "return _keep(source, index, out)"
DIGIT = "elif c.isdigit() and not _identifier_char_before(out):"
QUOTES = "**dict.fromkeys('\"`[', _scan_quoted),"  # the scanners of the three quoting characters
MUTANTS: dict[str, Mutant] = {
    "true": Mutant("return index + 4, True", KEEP, SURFACE, "visible"),
    "false": Mutant("return index + 5, True", KEEP, SURFACE, "visible"),
    "exponent": Mutant("return _skip_exponent(sql, cursor)", "return cursor", SURFACE, "shape"),
    "exponent_sign": Mutant('if cursor < length and sql[cursor] in "+-":', "if False:", SURFACE, "shape"),
    "doubled_quote": Mutant("if cursor + 1 < length and sql[cursor + 1] == closing:", "if False:", SURFACE, "shape"),
    # without the escape a run tokenises as if the backslash were deleted, so the readings agree and nothing cuts; the
    # recorder scans in MySQL mode, ``db_statement`` does not
    "backslash": Mutant('if c == "\\\\" and closing in', "if False and closing in", "recorder_sql-mysql", "visible"),
    "array_space": Mutant('subscript = subscript or out.ends_with_keyword(out.last_non_space(), "array")',
                          "subscript = subscript or False", "recorder_sql-generic", "shape"),
    # a name holding a quote is plain only on MySQL (r6): generic, a cut hides what follows it anyway
    "backtick": Mutant(QUOTES, QUOTES.replace("`", ""), "recorder_sql-mysql", "visible"),
    "bracket": Mutant(QUOTES, QUOTES.replace("[", ""), SURFACE, "shape"),
    "hash": Mutant('(mysql and sql[index] == "#")', "False", "db_statement-mysql", "visible"),
    "dollar": Mutant("return (end, True) if end > 0 else " + KEEP[7:], KEEP, SURFACE, "visible"),
    "unclosed_dollar": Mutant("return length if end < 0 else end + len(tag)",
                              "return -1 if end < 0 else end + len(tag)", SURFACE, "visible"),
    "leading_dot": Mutant('".": _scan_dot,', "", SURFACE, "visible"),
    "radix": Mutant('if sql[index] == "0" and (radix', "if False and (radix", SURFACE, "visible"),
    "underscore": Mutant('or (sql[cursor] == "_" and sql[cursor + 1 : cursor + 2].isdigit())', "", SURFACE, "visible"),
    "open_bracket": Mutant("if not runs or runs[-1][1] != end - index:", "if True:", "recorder_sql-generic", "visible"),
    "bracket_opener": Mutant("for stop in (found, _bracket_opener(scan)) if stop", "for stop in (found,) if stop",
                             "recorder_sql-generic", "visible"),
    "executable_comment": Mutant("return source.startswith(_EXECUTABLE_COMMENT, start)", "return False",
                                 "recorder_sql-mysql", "visible"),
    "tight_backtick": Mutant("_TIGHT_DASH_OPENER = re.compile(\"['\\\"`]|/\\\\*\")",
                             "_TIGHT_DASH_OPENER = re.compile(\"['\\\"]|/\\\\*\")", "recorder_sql-generic", "visible"),
    "tight_block_comment": Mutant("_TIGHT_DASH_OPENER = re.compile(\"['\\\"`]|/\\\\*\")",
                                  "_TIGHT_DASH_OPENER = re.compile(\"['\\\"`]\")", "recorder_sql-generic", "visible"),
    "backtick_cut": Mutant("found = _QUOTE_OR_BACKTICK.search(scan.source)", "found = _QUOTE.search(scan.source)",
                           "recorder_sql-generic", "visible"),
    "backtick_cut_mysql": Mutant("found = _QUOTE_OR_BACKTICK.search(scan.source)", "found = _QUOTE.search(scan.source)",
                                 "recorder_sql-mysql", "visible"),
    "hash_backtick": Mutant(', source.rfind("`"))', ")", "recorder_sql-generic", "visible"),
    "mysql_dollar": Mutant("end = -1 if mysql or _name_goes_on(", "end = -1 if _name_goes_on(",
                           "recorder_sql-mysql", "visible"),
    "number_dollar": Mutant('last == "?" and source[index - 1].isalnum()', "False", "recorder_sql-generic", "visible"),
    "dot_opens": Mutant('or last in "_$" or', 'or last in "_$." or', "recorder_sql-generic", "visible"),
    "backtick_quote": Mutant("if not mysql and _backtick_reads_two_ways(source, runs):", "if False:",
                             "recorder_sql-generic", "visible"),
    "at_dollar_cut": Mutant('source.startswith(("@$", ".$"), end - 1)', 'source.startswith(".$", end - 1)',
                            "recorder_sql-generic", "visible"),
    "dot_dollar_cut": Mutant('source.startswith(("@$", ".$"), end - 1)', 'source.startswith("@$", end - 1)',
                             "recorder_sql-generic", "visible"),
    "dot_dollar_holds": Mutant(' or ".$" in source', "", "recorder_sql-generic", "visible"),
    "cut_open_double_quote": Mutant("if mysql or end >= _MAX_SCAN_LENGTH:", "if mysql:", SURFACE, "visible"),
    "two_readings": Mutant("return _read(source.replace(", "return False and _read(source.replace(",
                           SURFACE, "visible"),
    "nested_comment": Mutant('if source.find("/*", start + 2, end) >= 0:', "if False:", SURFACE, "visible"),
    "alternative_quote": Mutant("if _ALTERNATIVE_QUOTE.search(source, start, end + 1):", "if False:",
                                SURFACE, "visible"),
    "hash_quote": Mutant('if 0 <= source.find("#", start, end) < last_quote:', "if False:", SURFACE, "visible"),
    # a digit or a keyword after a name character belongs to the name: over-masking ``col1`` lowers A1: A3 must catch it
    "digit_in_name": Mutant(DIGIT, DIGIT.replace(" and not _identifier_char_before(out)", ""), SURFACE, "shape"),
    "keyword_in_name": Mutant(
        "if _identifier_char_before(out):\n        return _keep(source, index, out)",
        "if False:\n        return _keep(source, index, out)",
        SURFACE,
        "shape",
    ),
    "in_collapse": Mutant('if "?" not in normalized:', "if True:", SURFACE, "shape"),
    # db.statement masks the text before it scans, which hides a vendor token anyway; the recorder scans first
    "double_quote_secret": Mutant(
        "or is_secret_value(sql[index + 1 : stop])", "or False", "recorder_sql-generic", "visible"
    ),
}  # fmt: skip


def _scratch_copy(tmp: Path) -> Path:
    """A copy of the ``sharpit`` package, without the built UI: the only tree a mutation is ever applied to."""
    package = Path(sqltrace.__file__).resolve().parents[2]
    copy = tmp / "src" / "sharpit"
    shutil.copytree(package, copy, ignore=shutil.ignore_patterns("__pycache__", "static"))
    return copy


def _mutate(copy: Path, mutant: Mutant) -> None:
    """``normalize``'s own module is the one that moves (``sqlscan.py`` from Task 2): find it, never name it."""
    package = Path(sqltrace.__file__).resolve().parents[2]
    relative = Path(sys.modules[sqltrace.normalize.__module__].__file__ or "").resolve().relative_to(package)
    target = copy / relative
    source = target.read_text(encoding="utf-8")
    assert source.count(mutant.anchor) == 1, f"anchor not found exactly once in {relative}: {mutant.anchor!r}"
    target.write_text(source.replace(mutant.anchor, mutant.replacement), encoding="utf-8")


def _run_worker(src: Path, surface: str) -> dict[str, int]:
    spec = json.dumps({"surface": surface, "rows": ROWS, "seeds": SEEDS})
    env = {**os.environ, "PYTHONPATH": str(src), "SHARPIT_MUTANT_SRC": str(src), "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run(
        [sys.executable, "-m", "tests.masking.mutant_worker", spec],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False, timeout=100,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def _base(surface: str) -> dict[str, int]:
    return mutant_worker.counts(surface, mutant_worker.rows_for(surface, ROWS, SEEDS))


def _kill(mutant: Mutant, tmp: Path) -> tuple[int, int]:
    """The failing-row count of the mutant's gate: unmutated, then mutated."""
    copy = _scratch_copy(tmp)
    _mutate(copy, mutant)
    return _base(mutant.surface)[mutant.gate], _run_worker(tmp / "src", mutant.surface)[mutant.gate]


@pytest.mark.parametrize("name", MUTANTS)
def test_every_lexer_branch_is_killed(name: str, tmp_path: Path) -> None:
    mutant = MUTANTS[name]
    base, mutated = _kill(mutant, tmp_path)
    print(f"mutant {name}: {mutant.gate} gate, {base} failing rows unmutated, {mutated} mutated")
    if mutated <= base:
        raise SurvivedMutant(f"{name} survives: {mutant.gate} gate {base} rows unmutated, {mutated} mutated")
