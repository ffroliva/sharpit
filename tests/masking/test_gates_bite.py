"""The masking gates can fail: planted builds and lexer mutants (spec A1, A3, revision 3; AGENTS.md retrospective).

A gate counts only after leaking and blanking builds both fail it. Revision 2's corpus let 11 lexer branches be deleted
without a failure, and an earlier generator scored 0 on builds leaking 17,000 of 30,000 statements.

* Planted builds: a surface that leaks, blanks or over-cuts must fail its gate on more rows than the real build does.
* Mutants: one source edit per lexer branch, applied to a scratch copy of ``src`` and run in a subprocess, never to
  the repo's files. A mutant is killed when it raises the gate's failing-row count above the unmutated build's, on the
  same rows. The gate is already red on head, so "turns it red" would prove nothing.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import types
from collections.abc import Callable
from dataclasses import fields
from functools import cache
from pathlib import Path
from typing import NamedTuple

import pytest
from tests.masking import mutant_worker, sql_corpus
from tests.masking import test_statement_surfaces as gates

from sharpit.engine import sqltext
from sharpit.engine.capture import sqlscan, sqltrace
from sharpit.engine.capture.errortext import render_error
from sharpit.engine.capture.statement import statement_text
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import Dialect
from sharpit.engine.sqltext import rules as rule_table

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


# Generic spans without dialect evidence fail closed; drive lexer gates through a known family.
SURFACE = "recorder_sql-mysql"
BASE_ROWS = sql_corpus.rows(7, ROWS, sql_corpus.MYSQL)


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
    _, carrier = gates.ERROR_SURFACES["recorder_error-mysql"]
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
    module: str = ""  # a path under the package, when the mutant is not in the lexer


LEXER_MODULE = "sharpit.engine.sqltext.lexer"  # where a mutant lands unless it names a module
FAMILY_MODULE = "engine/sqltext/family.py"
RENDER = "engine/sqltext/render.py"
FACADE = "engine/capture/sqlscan.py"
KEEP = "return _keep(source, index, out)"
DOT_DIGIT = ' or out.chars[-1] == "."'
DIGIT = "elif c.isdigit() and _number_can_start(out):"
NUMBER_START = f"    return not _identifier_char_before(out){DOT_DIGIT}\n"  # the test DIGIT hands to _number_can_start
QUOTES = "**dict.fromkeys('\"`[', _scan_quoted),"  # the scanners of the three quoting characters
CUT = "found = _RUN_OPENER.search(scan.source)"
NO_DOLLAR = 're.compile("[\'\\"`]")'  # the opener set without its dollar quote
MYSQL_TAG = "rules.dollar is DollarOpen.MYSQL_TAG"
CLOSER = "_no_step_back_closer(sql, tag, body_start) if no_step_back else sql.find(tag, body_start)"
CONFLICT_HIDES = (  # Task 35 moved the hide into _render's branch on a conflict or an open-quote ambiguity
    "    if block is not None and (ambiguous or (head.named is not None and head.named is not dialect)):\n"
    "        shown.append(_BLOCK_HIDDEN)\n"
    "        resume, link = _closing_link(text, block.end())\n"
    "    elif block is not None:\n"
    "        resume, link = _block(masker, text, block.end(), dialect, shown)\n"
)
UNREAD_HIDES = (  # what the mutants keep: the ambiguity's hide is not the switch
    "    if block is not None and ambiguous:\n"
    "        shown.append(_BLOCK_HIDDEN)\n"
    "        resume, link = _closing_link(text, block.end())\n"
    "    elif block is not None:\n"
)
DRIVER_SWITCH = Mutant(  # Task 28 turned the switch into a hide; the mutant puts the switch back
    CONFLICT_HIDES,
    UNREAD_HIDES + "        conflict = head.named is not None and head.named is not dialect\n"
    "        resume, link = _block(masker, text, block.end(), Dialect.MYSQL_FAMILY if conflict else dialect, shown)\n",
    "",
    "",
    "engine/sqltext/errors.py",
)
MUTANTS: dict[str, Mutant] = {
    "true": Mutant("return index + 4, True", KEEP, SURFACE, "visible"),
    "false": Mutant("return index + 5, True", KEEP, SURFACE, "visible"),
    "exponent": Mutant(
        "return _skip_exponent(sql, cursor, fail_unicode)",
        "return cursor",
        SURFACE,
        "shape",
        "engine/sqltext/numbers.py",
    ),
    "exponent_sign": Mutant(
        'if cursor < length and sql[cursor] in "+-":', "if False:", SURFACE, "shape", "engine/sqltext/numbers.py"
    ),
    "doubled_quote": Mutant("if cursor + 1 < length and sql[cursor + 1] == closing:", "if False:", SURFACE, "shape"),
    # without the escape a run tokenises as if the backslash were deleted, so the readings agree and nothing cuts; the
    # recorder scans in MySQL mode, ``db_statement`` does not
    "backslash": Mutant(
        'if c == "\\\\" and escaped and cursor + 1 < length:',
        "if False and cursor + 1 < length:",
        "recorder_sql-mysql",
        "visible",
    ),
    "array_space": Mutant('subscript = subscript or out.ends_with_keyword(out.last_non_space(), "array")',
                          "subscript = subscript or False", "recorder_sql-mysql", "shape"),
    # a name holding a quote is plain only on MySQL (r6): generic, a cut hides what follows it anyway
    "backtick": Mutant(QUOTES, QUOTES.replace("`", ""), "recorder_sql-mysql", "visible"),
    "bracket": Mutant(QUOTES, QUOTES.replace("[", ""), SURFACE, "shape"),
    "hash": Mutant('(rules.hash is HashRule.COMMENT and sql[index] == "#")', "False", "db_statement-mysql", "visible"),
    "dollar": Mutant("return (end, True) if end > 0 else " + KEEP[7:], KEEP, SURFACE, "visible"),
    "unclosed_dollar": Mutant("return length if end < 0 else end + len(tag)",
                              "return -1 if end < 0 else end + len(tag)", SURFACE, "visible"),
    "leading_dot": Mutant('".": _scan_dot,', "", SURFACE, "shape"),  # the digits hide anyway since r8: it shows ``.?``
    "radix": Mutant(
        'if sql[index] == "0" and (radix', "if False and (radix", SURFACE, "visible", "engine/sqltext/numbers.py"
    ),
    "underscore": Mutant(
        'or (sql[cursor] == "_" and sql[cursor + 1 : cursor + 2].isdigit())',
        "",
        SURFACE,
        "visible",
        "engine/sqltext/numbers.py",
    ),
    "open_bracket": Mutant("if not runs or runs[-1][1] != end - index:", "if True:", "recorder_sql-mysql", "visible"),
    "bracket_opener": Mutant("for stop in (found, _bracket_opener(scan)) if stop", "for stop in (found,) if stop",
                             "recorder_sql-mysql", "visible"),
    "executable_comment": Mutant(
        "return source.startswith(tuple(rules.executable_prefixes), start)",
        "return False",
        "recorder_sql-mysql",
        "visible",
    ),
    "backtick_cut": Mutant(CUT, "found = _QUOTE.search(scan.source)", "recorder_sql-mysql", "visible"),
    "backtick_cut_mysql": Mutant(CUT, "found = _QUOTE.search(scan.source)", "recorder_sql-mysql", "visible"),
    "dollar_cut": Mutant(CUT, f"found = {NO_DOLLAR}.search(scan.source)", "recorder_sql-mysql", "visible"),
    "mysql_dollar": Mutant(
        "end = _dollar_quote_end(source, index, rules)",
        f"end = -1 if {MYSQL_TAG} else _dollar_quote_end(source, index, rules)",
        "recorder_sql-mysql",
        "visible",
    ),
    # the family cut stops at a dollar quote, so these two only move the stop: the value stays hidden, the shape changes
    "mysql_dollar_name": Mutant(' or (rules.dot_digits_is_name and last == ".")', "", "recorder_sql-mysql", "shape"),
    "mysql_closer": Mutant(f"end = {CLOSER}",
                           "end = sql.find(tag, body_start)", "recorder_sql-mysql", "shape"),
    "mysql_digit_tag": Mutant("(digit_first or cursor > index + 1)", "(cursor > index + 1)", "recorder_sql-mysql",
                              "visible"),
    # the MySQL family: a statement that reads one way still stops where the two reads part
    "number_dollar": Mutant('last == "?" and source[index - 1].isalnum()', "False", "recorder_sql-mysql", "shape"),
    "bracket_digit_word": Mutant(
        '_BRACKET_IDENTIFIER = re.compile(r"\\[[^\\W\\d]\\w*(?: +[^\\W\\d]\\w*)* *\\]")',
        '_BRACKET_IDENTIFIER = re.compile(r"\\[\\w[\\w ]*\\]")',
        "recorder_sql-mysql",
        "visible",
    ),
    "cut_open_double_quote": Mutant(
        "if string or end >= _MAX_SCAN_LENGTH:", "if string:", "recorder_sql-mysql", "visible"
    ),
    "nested_comment": Mutant(
        'if rules.nested_comments is Reading.CUT and source.find("/*", start + 2, end) >= 0:',
        "if False:",
        "recorder_sql-mysql",
        "visible",
    ),
    # a digit or a keyword after a name character belongs to the name: over-masking ``col1`` lowers A1: A3 must catch it
    "digit_in_name": Mutant(DIGIT, "elif c.isdigit():", SURFACE, "shape"),
    "dot_digit": Mutant(NUMBER_START, NUMBER_START.replace(DOT_DIGIT, ""), SURFACE, "visible"),
    "dot_digit_mysql": Mutant(NUMBER_START, NUMBER_START.replace(DOT_DIGIT, ""), "recorder_sql-mysql", "visible"),
    # as ``mysql_dollar_name``: the ``$`` they free opens a quote, and the family cut stops there
    "name_part": Mutant("_skip_number(source, index, _name_part(out), fail_unicode)", "_skip_number(source, index)",
                        "recorder_sql-mysql", "shape"),
    "at_token": Mutant("if not rules.at_token or found is None:", "if True:", "recorder_sql-mysql", "shape"),
    "at_number": Mutant("if _AT_NUMBER.search(found[0]):", "if False:", "db_statement-mysql", "shape"),
    "release_name": Mutant('if flags[literal] and literal > start and source[literal - 1] == "=":', "if False:",
                           "db_statement-mysql", "shape", RENDER),
    "keyword_in_name": Mutant(
        "if _identifier_char_before(out):\n        return _keep(source, index, out)",
        "if False:\n        return _keep(source, index, out)",
        SURFACE,
        "shape",
    ),
    "ascii_space": Mutant("elif c in _SPACE:", "elif c.isspace():", "recorder_sql-mysql", "shape"),
    "ascii_space_collapse": Mutant("if c in _SPACE and collapse:", "if c.isspace() and collapse:", SURFACE, "shape",
                                   RENDER),
    "in_collapse": Mutant("if _PLACEHOLDER_RUN.search(normalized) is None:", "if True:", SURFACE, "shape", RENDER),
    # also dies on every surface's ``shape``: a masker hides the token as a mask where the scan left ``?``, so only the
    # scan alone shows it as ``visible``. Its one visible job in production is METADATA_ONLY, where no masker reads
    "double_quote_secret": Mutant("return is_secret_value(body)", "return False", "scan_alone-mysql", "visible",
                                  FACADE),
    # the lexer's hand-over: a ``"`` run it cannot place is a name to the renderer to judge, not code to copy at once
    "double_quoted_kind": Mutant("        return True\n    return None\n", "        return True\n    return False\n",
                                 "scan_alone-mysql", "visible"),
}  # fmt: skip


def _scratch_copy(tmp: Path) -> Path:
    """A copy of the ``sharpit`` package, without the built UI: the only tree a mutation is ever applied to."""
    package = Path(sqltrace.__file__).resolve().parents[2]
    copy = tmp / "src" / "sharpit"
    shutil.copytree(package, copy, ignore=shutil.ignore_patterns("__pycache__", "static"))
    return copy


def _mutate(copy: Path, mutant: Mutant) -> Path:
    """Apply ``mutant`` to ``copy``: the lexer unless it names a module, which is found by name, never by path.

    ``sqlscan.py`` forwards since Task 11, so ``sqltrace.normalize.__module__`` is no longer the lexer's address.
    Returns the file written, so a test can tell it is a module the entry points run.
    """
    package = Path(sqltrace.__file__).resolve().parents[2]
    lexer = Path(importlib.import_module(LEXER_MODULE).__file__ or "").resolve().relative_to(package)
    relative = Path(mutant.module) if mutant.module else lexer
    target = copy / relative
    source = target.read_text(encoding="utf-8")
    assert source.count(mutant.anchor) == 1, f"anchor not found exactly once in {relative}: {mutant.anchor!r}"
    target.write_text(source.replace(mutant.anchor, mutant.replacement), encoding="utf-8")
    return target


def _worker_env(src: Path) -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(src), "SHARPIT_MUTANT_SRC": str(src), "PYTHONDONTWRITEBYTECODE": "1"}


def _run_worker(src: Path, surface: str, seeds: tuple[int, ...] = SEEDS) -> dict[str, int]:
    spec = json.dumps({"surface": surface, "rows": ROWS, "seeds": seeds})
    done = subprocess.run(
        [sys.executable, "-m", "tests.masking.mutant_worker", spec],
        cwd=ROOT, env=_worker_env(src), capture_output=True, text=True, check=False, timeout=100,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@cache
def _base(surface: str, seeds: tuple[int, ...] = SEEDS) -> dict[str, int]:
    return mutant_worker.counts(surface, mutant_worker.rows_for(surface, ROWS, seeds))


def _kill(mutant: Mutant, tmp: Path, seeds: tuple[int, ...] = SEEDS) -> tuple[int, int]:
    """The failing-row count of the mutant's gate: unmutated, then mutated."""
    copy = _scratch_copy(tmp)
    _mutate(copy, mutant)
    return _base(mutant.surface, seeds)[mutant.gate], _run_worker(tmp / "src", mutant.surface, seeds)[mutant.gate]


def test_each_mutant_runs_on_an_otherwise_pristine_tree(tmp_path: Path) -> None:
    package = Path(sqltrace.__file__).resolve().parents[2]
    copy = _scratch_copy(tmp_path)
    target = _mutate(copy, MUTANTS["array_space"]).relative_to(copy)
    expected = {
        path.relative_to(package): path.read_bytes()
        for path in package.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and "static" not in path.parts
    }
    actual = {path.relative_to(copy): path.read_bytes() for path in copy.rglob("*") if path.is_file()}
    assert {path: contents for path, contents in actual.items() if path != target} == {
        path: contents for path, contents in expected.items() if path != target
    }


def test_the_mutated_module_is_never_loaded_from_cached_bytecode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mutant = MUTANTS["array_space"]
    copy = _scratch_copy(tmp_path)
    target = _mutate(copy, mutant)
    module = ".".join(target.relative_to(copy).with_suffix("").parts)
    marker = mutant.replacement
    prefix = tmp_path / "pycache"
    monkeypatch.setenv("PYTHONPYCACHEPREFIX", str(prefix))
    env = _worker_env(copy.parent)
    probe = (
        "import importlib,json,pathlib,sys; m=importlib.import_module('sharpit." + module + "'); "
        "print(json.dumps({'file':m.__file__,'cached':m.__cached__,'marker':"
        + repr(marker)
        + " in pathlib.Path(m.__file__).read_text(encoding='utf-8'),'prefix':sys.pycache_prefix}))"
    )
    done = subprocess.run(
        [sys.executable, "-c", probe], cwd=ROOT, env=env, capture_output=True, text=True, check=False, timeout=30
    )
    assert done.returncode == 0, done.stderr[-2000:]
    loaded = json.loads(done.stdout.strip().splitlines()[-1])
    assert Path(loaded["file"]).resolve() == target.resolve(), "mutated module did not load from scratch source"
    assert loaded["marker"], "loaded source does not contain the mutation marker"
    assert not list(copy.parent.rglob("*.pyc")), "bytecode was written under the scratch tree"
    assert loaded["prefix"] == str(prefix), "probe did not use the worker's pycache prefix"
    assert not list(prefix.rglob("*.pyc")), "bytecode was written under pycache prefix"


def test_the_unmutated_counts_are_computed_once_per_surface(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _base.cache_clear()
    calls = 0
    counts = mutant_worker.counts

    def counted(surface: str, rows: object) -> dict[str, int]:
        nonlocal calls
        calls += 1
        return counts(surface, rows)  # type: ignore[arg-type]

    monkeypatch.setattr(mutant_worker, "counts", counted)
    for index, name in enumerate(("true", "false", "hash")):
        _kill(MUTANTS[name], tmp_path / str(index))
    assert calls == 2, "one unmutated baseline is required for each surface"


# mutants the seeded rows cannot reach (the cut hides what they change): a named unit test must fail on the mutated copy
NEVER_CLOSES = Mutant(
    f"end = {CLOSER}",
    "end = -1 if no_step_back else sql.find(tag, body_start)",
    "recorder_sql-mysql",
    "shape",
)  # the gates at seeds 7, 8 and 9 let it live: the family cut hides everything past an opener
CANDIDATE_PREDICATE = Mutant(
    "Candidate(len(out.chars), out.predicate_position())",
    "Candidate(len(out.chars), False)",
    "scan_alone-mysql",
    "shape",
)  # the predicate count is no gate's row: only the lexer's own test sees it
CLOSER_DIALECT = Mutant(
    "_read(text[:_MAX_SCAN_LENGTH], readings(dialect)[0]), text)",
    "_read(text[:_MAX_SCAN_LENGTH], READINGS[Dialect.POSTGRESQL][0]), text)",
    "scan_alone-mysql",
    "shape",
)  # no row reads a ``[SQL: `` block: only the lexer's own test sees which dialect ``block_closer`` is given
TWO_WAYS_DIALECT = Mutant(
    "rule_sets = readings(dialect)",
    "rule_sets = READINGS[Dialect.SQLITE]",
    "scan_alone-mysql",
    "shape",
)  # likewise for ``reads_two_ways``
TOKEN_GATE_SKIPS_ALL = Mutant("if _SECRET_HINT.search(tracked.text):", "if False:", "", "", "engine/masking.py")
TOKEN_GATE_SKIPS_EACH = Mutant("if _SECRET_HINT.search(token) is None:", "if True:", "", "", "engine/masking.py")
TOKEN_GATE_TEST = "tests/engine/test_masking_token_gate.py::test_a_secret_the_gate_could_miss_is_still_masked"
# each field gates its own cut: with it read away MySQL text stops where only generic text stops, and no row holds that
RENDER_PREDICATE = Mutant(
    "predicates += candidate.predicate", "predicates += False", "scan_alone-mysql", "shape", RENDER
)
SQLITE_DOUBLE_QUOTE = Mutant("if scan.hide_double_quoted:", "if False:", "scan_alone-mysql", "shape", RENDER)
SQLITE_SUFFIX = Mutant('elif c == "(":', "elif False:", "scan_alone-mysql", "shape")
SQLITE_SUFFIX_SPACE = Mutant(
    'source[cursor] not in _SPACE and source[cursor] != ")"',
    'source[cursor] != " " and source[cursor] != ")"',
    "",
    "",
)
SQLITE_SUFFIX_NONASCII = Mutant(
    'if c.isalnum() or c == "_" or c == "$" or not c.isascii():',
    'if c.isalnum() or c == "_" or c == "$":',
    "",
    "",
)
SQLITE_SUFFIX_NAMESPACE = Mutant(
    'elif c == ":" and cursor + 1 < length and source[cursor + 1] == ":":',
    "elif False:",
    "",
    "",
)
SQLITE_SUFFIX_EMPTY = Mutant(
    "    if n == 0:\n        return _keep(source, index, out)",
    "    if False:\n        return _keep(source, index, out)",
    "",
    "",
)
SQLITE_BACKSLASH = Mutant(
    "escaped = _escapes_in_quoted(sql, index, closing, rules)",
    "escaped = True",
    "",
    "",
)
SQLITE_BRACKET = Mutant(
    "if rules.bracket is Bracket.TO_FIRST_CLOSE:",
    "if False:",
    "",
    "",
)
PG_NESTED_COMMENTS = Mutant("if rules.nested_comments is Reading.YES:", "if False:", "", "")
PG_EXECUTABLE_PREFIXES = Mutant(
    "executable_prefixes=frozenset(),  # scan.l:328, plain comments",
    'executable_prefixes=frozenset({"/*!"}),  # scan.l:328, plain comments',
    "",
    "",
    "engine/sqltext/rules.py",
)
PG_CUT_BRACKET_RULE = Mutant(
    "cut_bracket=False,\n    executable_prefixes=frozenset(),  # scan.l:328, plain comments",
    "cut_bracket=True,\n    executable_prefixes=frozenset(),  # scan.l:328, plain comments",
    "",
    "",
    "engine/sqltext/rules.py",
)
PG_CR_ENDS_DASH = Mutant("if rules.cr_ends_dash is Reading.YES:", "if False:", "", "")
PG_DIGIT_DOLLAR = Mutant("return index, True  # ambiguous", "return end, True  # ambiguous", "", "")
PG_BRACKET_CHAR = Mutant(
    'if source[index] == "[" and rules.bracket is Bracket.CHARACTER and not rules.cut_bracket:\n'
    "        return _keep(source, index, out)",
    "if False:\n        return _keep(source, index, out)",
    "",
    "",
)
PG_BACKTICK_NONE = Mutant(
    'if source[index] == "`" and rules.backtick_run is BacktickRun.NONE:\n        return _keep(source, index, out)',
    "if False:\n        return _keep(source, index, out)",
    "",
    "",
)
PG_CUT_BACKSLASH = Mutant(
    "return rules.cut_backslash and _backslash_reads_two_ways(scan, rules)", "return False", "", ""
)
PG_ESCAPES_IN_QUOTED_E = Mutant(
    'if rules.backslash_in_single is Backslash.E_ONLY:\n        prefix = index > 0 and sql[index - 1] in "eE"',
    'if False:\n        prefix = index > 0 and sql[index - 1] in "eE"',
    "",
    "",
)
PG_BACKSLASH_TWO_WAYS_E = Mutant(
    "if rules.backslash_in_single is Backslash.E_ONLY:\n"
    "        return _read(source, _escaping_single(rules)).out.text() != scan.out.text()",
    "if False:\n        return False",
    "",
    "",
)
PG_ASCII_E_BOUNDARY = Mutant(
    "not sql[index - 2].isascii() or sql[index - 2].isalnum()",
    "sql[index - 2].isalnum()",
    "",
    "",
)
PG_PLACEHOLDER_BEFORE_DOLLAR_QUOTE = Mutant(
    "return index, True  # ambiguous",
    "return _keep(source, index, out)  # ambiguous",
    "",
    "",
)
PG_DOLLAR_NAME_BOUNDARY = Mutant(
    "dollar_name_boundary=True,",
    "dollar_name_boundary=False,",
    "",
    "",
    "engine/sqltext/rules.py",
)
PG_FIRST_LINE_ENDING = Mutant("min(lf, cr)", "lf", "", "")
MYSQL_BRACKET_CUT = Mutant(
    "and rules.bracket is Bracket.CHARACTER and not rules.cut_bracket:",
    "and rules.bracket is Bracket.CHARACTER:",
    "",
    "",
)
MYSQL_NESTED_COMMENT_CUT = Mutant(
    'if rules.nested_comments is Reading.CUT and source.find("/*", start + 2, end) >= 0:',
    "if False:",
    "",
    "",
)
SQLITE_VARIABLE_BOUNDARY = Mutant(
    "if not _opens_a_token(source, index):\n        return index, True\n    if suffix:", "if suffix:", "", ""
)
SQLITE_OPEN_SUFFIX = Mutant(
    """in source[opening:cursor]:\n        return -1""",
    """in source[opening:cursor]:\n        return cursor""",
    "",
    "",
)
SQLITE_QUOTED_SUFFIX = Mutant(
    """ or "'" in source[opening:cursor] or '"' in source[opening:cursor]:""",
    ":",
    "",
    "",
)
SQLITE_DOUBLE_QUOTED_SUFFIX = Mutant(""" or '"' in source[opening:cursor]:""", ":", "", "")
SQLITE_CUT_IS_A_GUESS = Mutant(
    "variable_cut = rule_sets[0].variable_suffix is VariableSuffix.TCL_PAREN and scan.cut >= 0",
    "variable_cut = False",
    "",
    "",
)
SQLITE_BOM_SPACE = Mutant(
    'elif rules.variable_suffix is VariableSuffix.TCL_PAREN and c == "\\ufeff":',
    "elif False:",
    "",
    "",
)
MYSQL_M_BANG_RULE = Mutant(
    'dollar_closer=DollarCloser.NONE,\n    executable_prefixes=frozenset({"/*!", "/*M!"}),',
    'dollar_closer=DollarCloser.NONE,\n    executable_prefixes=frozenset({"/*!"}),',
    "",
    "",
    "engine/sqltext/rules.py",
)
MYSQL_M_BANG_CUT = Mutant(
    "return source.startswith(tuple(rules.executable_prefixes), start)",
    'return source.startswith(("/*!",), start)',
    "",
    "visible",
)
FAMILY = "tests/engine/sqltext/test_rules_mysql_family.py"
SHRUNK = "test_a_value_some_real_reading_holds_never_shows"
RULES_PY = "engine/sqltext/rules.py"
FAMILY_CUT = Mutant(
    "cuts += [family_cut(scan, _read(source, other), _LITERAL) for other in parting]",
    "",
    "",
    "",
    "engine/sqltext/lexer.py",
)
FAMILY_SECOND_READ = Mutant("    return rule_sets[1:] + session\n", "    return ()\n", "", "", FAMILY_MODULE)
FAMILY_HEAD = Mutant(
    "parted = (family_cut(shown, _read(source[:cut], other), _LITERAL) for other in parting)",
    "parted = ()",
    "",
    "",
    "engine/sqltext/lexer.py",
)
FAMILY_SESSION = Mutant("    return rule_sets[1:] + session\n", "    return rule_sets[1:]\n", "", "", FAMILY_MODULE)
FAMILY_TWO_WAYS = Mutant(
    "return variable_cut or _statement_cut(scan, rule_sets) >= 0",
    "variable_cut or _ambiguous_cut(scan, rule_sets[0]) >= 0",
    "",
    "",
    "engine/sqltext/lexer.py",
)
MYSQL_T_BANG_RULE = Mutant('cut_prefixes=frozenset({"/*T!"})', "cut_prefixes=frozenset()", "", "", RULES_PY)
MYSQL_BRACKET_RULE = Mutant(
    "    cut_bracket=True,  # MariaDB `sql_mode=MSSQL` is session state no text reveals",
    "    cut_bracket=False,  # MariaDB `sql_mode=MSSQL` is session state no text reveals",
    "",
    "",
    RULES_PY,
)
MARIADB_DOLLAR = Mutant(
    "if rules.dollar is DollarOpen.NONE:\n        return -1",
    "if False:\n        return -1",
    "",
    "",
    "engine/sqltext/lexer.py",
)
MARIADB_BACKSLASH = Mutant("backslash_token=True,", "backslash_token=False,", "", "", RULES_PY)
MYSQL_REAL_DOLLAR = Mutant(
    "if number and rules.digit_dollar is DigitDollar.NAME and _real_number(",
    "if False and _real_number(",
    "",
    "",
    "engine/sqltext/lexer.py",
)
MYSQL_BAD_EXPONENT = Mutant(
    "cuts.extend((_bad_exponent_cut(scan), _uncertain_number_cut(source, literals)))",
    "cuts.extend((-1, _uncertain_number_cut(source, literals)))",
    "",
    "",
    "engine/sqltext/lexer.py",
)
MYSQL_UNCERTAIN_NUMBER = Mutant("_uncertain_number_cut(source, literals)", "-1", "", "", "engine/sqltext/lexer.py")
MYSQL_SIGNED_EXPONENT = Mutant("|[eE][+-]\\d+(?=[\\w.$\\x80-\\U0010ffff])", "", "", "", "engine/sqltext/lexer.py")
MYSQL_ASCII_HOST = Mutant('r"@[0-9A-Za-z_.$]+"', 'r"@[\\w.$\\x80-\\U0010ffff]+"', "", "", "engine/sqltext/lexer.py")
MYSQL_DOUBLED_BRACKET = Mutant('and source.startswith("]", end):', "and False:", "", "", "engine/sqltext/lexer.py")
MYSQL_BRACKET_LITERAL_SKIP = Mutant(
    "if literal and literal[0] <= index < literal[1]:", "if False:", "", "", "engine/sqltext/lexer.py"
)
MYSQL_BRACKET_PAIR = Mutant('elif source.startswith("]]", index):', "elif False:", "", "", "engine/sqltext/lexer.py")
MYSQL_BRACKET_PUSH = Mutant("openings.append(index)", "pass", "", "", "engine/sqltext/lexer.py")
MYSQL_BRACKET_POP = Mutant("openings.pop()", "pass", "", "", "engine/sqltext/lexer.py")
MYSQL_BRACKET_EARLIEST = Mutant("return openings[0]", "return openings[-1]", "", "", "engine/sqltext/lexer.py")
MYSQL_DOUBLE_QUOTED_KEY = Mutant(
    "if rules.double_quote is DoubleQuote.STRING and _KEY_COLON.match(source, end):",
    "if False:",
    "",
    "",
    "engine/sqltext/lexer.py",
)
MYSQL_SYSTEM_VARIABLE = Mutant(
    '(_SYSTEM_VARIABLE if source[index - 1 : index] == "@" else _AT_TOKEN).match(source, index)',
    "_AT_TOKEN.match(source, index)",
    "",
    "",
    "engine/sqltext/lexer.py",
)
NAMED_MUTANTS = {
    "array_space": MUTANTS["array_space"],
    "bracket_digit_word": MUTANTS["bracket_digit_word"],
    "open_bracket": MUTANTS["open_bracket"],
    "token_gate_skips_all": TOKEN_GATE_SKIPS_ALL,
    "token_gate_skips_each": TOKEN_GATE_SKIPS_EACH,
    "mysql_closer_never": NEVER_CLOSES,
    # Task 29: the generic rows reached these on the corpus; on a known dialect a unit test does
    "dollar_cut": MUTANTS["dollar_cut"],
    "cut_open_double_quote": MUTANTS["cut_open_double_quote"],
    "double_quote_secret": MUTANTS["double_quote_secret"],
    "double_quoted_kind": MUTANTS["double_quoted_kind"],
    "nested_comment": MUTANTS["nested_comment"],
    "bracket_opener": MUTANTS["bracket_opener"],
    "mysql_closer": MUTANTS["mysql_closer"],
    "family_cut": FAMILY_CUT,
    "family_second_read": FAMILY_SECOND_READ,
    "family_head": FAMILY_HEAD,
    "family_session": FAMILY_SESSION,
    "family_two_ways": FAMILY_TWO_WAYS,
    "mysql_driver_switch": DRIVER_SWITCH,
    "candidate_predicate": CANDIDATE_PREDICATE,
    "closer_dialect": CLOSER_DIALECT,
    "two_ways_dialect": TWO_WAYS_DIALECT,
    "render_predicate": RENDER_PREDICATE,
    "sqlite_double_quote": SQLITE_DOUBLE_QUOTE,
    "sqlite_d6_shows": SQLITE_DOUBLE_QUOTE,
    "sqlite_suffix": SQLITE_SUFFIX,
    "suffix_stops_at_space_only": SQLITE_SUFFIX_SPACE,
    "nonascii_not_name": SQLITE_SUFFIX_NONASCII,
    "namespace_off": SQLITE_SUFFIX_NAMESPACE,
    "dollar_not_name": SQLITE_VARIABLE_BOUNDARY,
    "sqlite_backslash_escape": SQLITE_BACKSLASH,
    "sqlite_bracket_rule": SQLITE_BRACKET,
    "unclosed_suffix_visible": SQLITE_OPEN_SUFFIX,
    "quoted_suffix": SQLITE_QUOTED_SUFFIX,
    "double_quoted_suffix": SQLITE_DOUBLE_QUOTED_SUFFIX,
    "n_zero_guard_off": SQLITE_SUFFIX_EMPTY,
    "variable_cut_is_a_guess": SQLITE_CUT_IS_A_GUESS,
    "bom_is_space": SQLITE_BOM_SPACE,
    "pg_nested_comments": PG_NESTED_COMMENTS,
    "pg_executable_prefixes": PG_EXECUTABLE_PREFIXES,
    "pg_cut_bracket_rule": PG_CUT_BRACKET_RULE,
    "pg_cr_ends_dash": PG_CR_ENDS_DASH,
    "pg_digit_dollar": PG_DIGIT_DOLLAR,
    "pg_bracket_char": PG_BRACKET_CHAR,
    "pg_backtick_none": PG_BACKTICK_NONE,
    "pg_cut_backslash": PG_CUT_BACKSLASH,
    "pg_escapes_in_quoted_e": PG_ESCAPES_IN_QUOTED_E,
    "pg_backslash_two_ways_e": PG_BACKSLASH_TWO_WAYS_E,
    "pg_ascii_e_boundary": PG_ASCII_E_BOUNDARY,
    "pg_placeholder_before_dollar_quote": PG_PLACEHOLDER_BEFORE_DOLLAR_QUOTE,
    "pg_dollar_name_boundary": PG_DOLLAR_NAME_BOUNDARY,
    "pg_first_line_ending": PG_FIRST_LINE_ENDING,
    "mysql_bracket_cut": MYSQL_BRACKET_CUT,
    "mysql_nested_comment_cut": MYSQL_NESTED_COMMENT_CUT,
    "mysql_m_bang_cut": MYSQL_M_BANG_CUT,
    "mysql_m_bang_rule": MYSQL_M_BANG_RULE,
    "mysql_t_bang_rule": MYSQL_T_BANG_RULE,
    "mysql_bracket_rule": MYSQL_BRACKET_RULE,
    "mariadb_dollar_none": MARIADB_DOLLAR,
    "mariadb_backslash": MARIADB_BACKSLASH,
    "mysql_real_dollar": MYSQL_REAL_DOLLAR,
    "mysql_bad_exponent": MYSQL_BAD_EXPONENT,
    "mysql_uncertain_number": MYSQL_UNCERTAIN_NUMBER,
    "mysql_signed_exponent": MYSQL_SIGNED_EXPONENT,
    "mysql_ascii_host": MYSQL_ASCII_HOST,
    "mysql_doubled_bracket": MYSQL_DOUBLED_BRACKET,
    "mysql_bracket_literal_skip": MYSQL_BRACKET_LITERAL_SKIP,
    "mysql_bracket_pair": MYSQL_BRACKET_PAIR,
    "mysql_bracket_push": MYSQL_BRACKET_PUSH,
    "mysql_bracket_pop": MYSQL_BRACKET_POP,
    "mysql_bracket_earliest": MYSQL_BRACKET_EARLIEST,
    "mysql_double_quoted_key": MYSQL_DOUBLE_QUOTED_KEY,
    "mysql_system_variable": MYSQL_SYSTEM_VARIABLE,
}
CLOSED_QUOTE = "tests/engine/sqltext/test_lexer.py::test_mysql_dollar_closer_does_not_step_back_after_a_partial_match"
PREDICATE = (
    "tests/engine/sqltext/test_lexer.py::test_a_candidate_remembers_whether_a_literal_there_would_sit_in_a_predicate"
)
NAMED_TESTS = {
    "array_space": "tests/engine/sqltext/test_lexer.py::test_array_subscript_is_not_a_bracket_identifier",
    "bracket_digit_word": "tests/engine/sqltext/test_lexer.py::test_a_digit_led_bracket_body_is_not_an_identifier",
    "open_bracket": "tests/engine/sqltext/test_lexer.py::test_an_open_quote_at_bracket_close_opens_a_two_way_read",
    "token_gate_skips_all": TOKEN_GATE_TEST,
    "token_gate_skips_each": TOKEN_GATE_TEST,
    "mysql_closer_never": CLOSED_QUOTE,
    "dollar_cut": "tests/engine/capture/test_sqlscan.py::test_a_cut_stops_at_a_dollar_quote",
    "cut_open_double_quote": (
        "tests/engine/capture/test_sqlscan.py::test_a_double_quote_cut_open_at_the_scan_limit_is_a_literal"
    ),
    "double_quote_secret": "tests/engine/capture/test_sqltrace.py::test_double_quoted_secret_is_a_literal_anywhere",
    "double_quoted_kind": "tests/engine/sqltext/test_lexer.py::test_a_double_quoted_run_is_its_own_kind",
    "nested_comment": (
        "tests/engine/capture/test_sqlscan.py::test_a_nested_comment_and_a_differing_backslash_cut_on_mysql"
    ),
    "bracket_opener": "tests/engine/capture/test_sqlscan.py::test_a_run_left_open_in_a_bracket_stops_the_statement",
    "mysql_closer": CLOSED_QUOTE,
    "family_cut": f"{FAMILY}::test_family_cut_witness[7-dollar]",
    "family_second_read": f"{FAMILY}::test_family_cut_witness[7-dollar]",
    "family_head": f"{FAMILY}::test_family_cut_witness[7-head]",
    "family_session": f"{FAMILY}::test_family_cut_witness[7-session]",
    "family_two_ways": f"{FAMILY}::test_reads_two_ways_sees_where_the_readings_part",
    "mysql_driver_switch": "tests/masking/test_error_regions.py::test_a_driver_line_chooses_no_reading",
    "candidate_predicate": PREDICATE,
    "closer_dialect": "tests/engine/sqltext/test_lexer.py::test_block_closer_reads_the_dialect_it_is_given",
    "two_ways_dialect": "tests/engine/sqltext/test_lexer.py::test_reads_two_ways_reads_the_dialect_it_is_given",
    "render_predicate": "tests/engine/sqltext/test_render.py::test_a_secret_run_in_a_predicate_is_a_predicate_literal",
    "sqlite_double_quote": (
        "tests/engine/sqltext/test_rules_sqlite.py::test_sqlite_hides_every_double_quoted_run[select_x]"
    ),
    "sqlite_d6_shows": "tests/masking/test_statement_surfaces.py::test_every_sqlite_d6_row_is_hidden[recorder_sql]",
    "sqlite_suffix": (
        "tests/engine/sqltext/test_rules_sqlite.py::test_a_quote_in_a_suffix_or_an_open_suffix_hides_from_the_opener[colon]"
    ),
    "suffix_stops_at_space_only": (
        "tests/engine/sqltext/test_rules_sqlite.py::test_sqlite_tcl_suffix_boundaries[ascii_space]"
    ),
    "nonascii_not_name": (
        "tests/engine/sqltext/test_rules_sqlite.py::test_sqlite_tcl_suffix_boundaries[nonascii_name]"
    ),
    "namespace_off": ("tests/engine/sqltext/test_rules_sqlite.py::test_sqlite_tcl_suffix_boundaries[namespace]"),
    "dollar_not_name": (
        "tests/engine/sqltext/test_rules_sqlite.py::test_every_opener_cuts_when_its_source_character_is_not_a_boundary[dollar]"
    ),
    "sqlite_backslash_escape": (
        "tests/engine/sqltext/test_rules_sqlite.py::test_sqlite_backslash_does_not_join_adjacent_literals"
    ),
    "sqlite_bracket_rule": (
        "tests/engine/sqltext/test_rules_sqlite.py::test_sqlite_never_shows_a_returned_tcl_name_value[colon_in_bracket]"
    ),
    "unclosed_suffix_visible": (
        "tests/engine/sqltext/test_rules_sqlite.py::test_a_quote_in_a_suffix_or_an_open_suffix_hides_from_the_opener[open_at_space]"
    ),
    "quoted_suffix": (
        "tests/engine/sqltext/test_rules_sqlite.py::test_a_quote_in_a_suffix_or_an_open_suffix_hides_from_the_opener[colon]"
    ),
    "double_quoted_suffix": (
        "tests/engine/sqltext/test_rules_sqlite.py::test_a_quote_in_a_suffix_or_an_open_suffix_hides_from_the_opener[at_double]"
    ),
    "n_zero_guard_off": (
        "tests/engine/sqltext/test_rules_sqlite.py::test_sqlite_tcl_suffix_boundaries[no_name_no_cut]"
    ),
    "variable_cut_is_a_guess": (
        "tests/engine/sqltext/test_rules_sqlite.py::test_a_block_closer_past_a_variable_cut_is_a_guess"
    ),
    "bom_is_space": ("tests/engine/sqltext/test_rules_sqlite.py::test_sqlite_bom_is_space_at_a_token_start"),
    "pg_nested_comments": "tests/engine/sqltext/test_rules_postgresql.py::test_nested_gate_row",
    "pg_executable_prefixes": (
        "tests/engine/sqltext/test_rules_postgresql.py::test_executable_comment_prefix_is_not_postgresql_syntax"
    ),
    "pg_cut_bracket_rule": "tests/engine/sqltext/test_rules_postgresql.py::test_bracket_is_character",
    "pg_cr_ends_dash": "tests/engine/sqltext/test_rules_postgresql.py::test_line_comment_ends_at_cr_or_lf",
    "pg_digit_dollar": "tests/engine/sqltext/test_rules_postgresql.py::test_dollar_after_number_opens_quote",
    "pg_bracket_char": "tests/engine/sqltext/test_rules_postgresql.py::test_bracket_is_character",
    "pg_backtick_none": "tests/engine/sqltext/test_rules_postgresql.py::test_backtick_is_operator",
    "pg_cut_backslash": "tests/engine/sqltext/test_rules_postgresql.py::test_a_postgresql_backslash_keeps_its_cut",
    "pg_escapes_in_quoted_e": "tests/engine/sqltext/test_rules_postgresql.py::test_escape_string_constant",
    "pg_backslash_two_ways_e": (
        "tests/engine/sqltext/test_rules_postgresql.py::test_a_postgresql_backslash_keeps_its_cut"
    ),
    "pg_ascii_e_boundary": (
        "tests/engine/sqltext/test_rules_postgresql.py::test_non_ascii_identifier_before_e_does_not_make_an_escape_string"
    ),
    "pg_placeholder_before_dollar_quote": (
        "tests/engine/sqltext/test_rules_postgresql.py::test_asyncpg_placeholders_stay_placeholders"
    ),
    "pg_dollar_name_boundary": (
        "tests/engine/sqltext/test_rules_postgresql.py::test_dollar_quotes_after_ascii_boundaries_and_ambiguous_dollars"
    ),
    "pg_first_line_ending": "tests/engine/sqltext/test_rules_postgresql.py::test_line_comment_ends_at_cr_or_lf",
    "mysql_bracket_cut": "tests/engine/capture/test_sqlscan.py::test_the_other_cuts_stand_on_a_text_holding_a_dollar",
    "mysql_nested_comment_cut": (
        "tests/engine/capture/test_sqlscan.py::test_a_nested_comment_and_a_differing_backslash_cut_on_mysql"
    ),
    "mysql_m_bang_cut": (
        "tests/engine/capture/test_sqlscan.py::test_an_executable_comment_ends_later_than_the_scan_reads"
    ),
    "mysql_m_bang_rule": f"{FAMILY}::test_family_cut_witness[7-m_bang]",
    "mysql_t_bang_rule": f"{FAMILY}::test_family_cut_witness[7-tidb]",
    "mysql_bracket_rule": f"{FAMILY}::test_family_keeps_the_bracket_cut",
    "mariadb_dollar_none": f"{FAMILY}::test_mariadb_does_not_open_a_dollar_quote",
    "mariadb_backslash": f"{FAMILY}::test_family_cut_witness[7-escape]",
    "mysql_real_dollar": f"{FAMILY}::test_family_cut_witness[7-real_dollar]",
    "mysql_bad_exponent": f"{FAMILY}::test_family_cut_witness[7-bad_exponent]",
    "mysql_uncertain_number": f"{FAMILY}::test_uncertain_mysql_number_read_cuts_at_number[underscore-exponent]",
    "mysql_signed_exponent": f"{FAMILY}::test_family_cut_witness[7-signed_exponent]",
    "mysql_ascii_host": f"{FAMILY}::{SHRUNK}[mysql84-a_host_is_ascii]",
    "mysql_doubled_bracket": (
        "tests/engine/sqltext/test_lexer.py::test_mssql_doubled_bracket_opener_cuts_the_raw_mysql_pass"
    ),
    "mysql_bracket_literal_skip": (
        "tests/engine/sqltext/test_rules_mysql_family.py::test_a_bracket_inside_a_string_does_not_start_a_family_cut"
    ),
    "mysql_bracket_pair": (
        "tests/engine/sqltext/test_rules_mysql_family.py::test_a_mssql_doubled_bracket_cuts_at_the_earliest_matching_opener[nested]"
    ),
    "mysql_bracket_push": (
        "tests/engine/sqltext/test_rules_mysql_family.py::test_a_mssql_doubled_bracket_cuts_at_the_earliest_matching_opener[subscript]"
    ),
    "mysql_bracket_pop": (
        "tests/engine/sqltext/test_rules_mysql_family.py::test_a_mssql_doubled_bracket_cuts_at_the_earliest_matching_opener[second-subscript]"
    ),
    "mysql_bracket_earliest": (
        "tests/engine/sqltext/test_rules_mysql_family.py::test_a_mssql_doubled_bracket_cuts_at_the_earliest_matching_opener[nested]"
    ),
    "mysql_double_quoted_key": f"{FAMILY}::test_family_cut_witness[7-key]",
    "mysql_system_variable": f"{FAMILY}::test_family_cut_witness[7-system_variable]",
}


CRASH = re.compile(r"\b(?:UnboundLocal|Name|Attribute|Type|Syntax|Index|Key)Error\b")  # a crash is not a red


def _assert_named_mutant_fails(name: str, tmp_path: Path) -> None:
    copy = _scratch_copy(tmp_path)
    _mutate(copy, NAMED_MUTANTS[name])
    env = {**os.environ, "PYTHONPATH": str(tmp_path / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run(
        [sys.executable, "-m", "pytest", NAMED_TESTS[name], "-q", "-p", "no:cacheprovider", "-p", "no:xdist"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False, timeout=100,
    )  # fmt: skip
    assert done.returncode == 1, f"{name} survives its named test: {done.stdout[-1500:]}"
    assert not CRASH.search(done.stdout), f"{name} crashed its test, which proves nothing: {done.stdout[-1500:]}"


@pytest.mark.parametrize("name", NAMED_TESTS)
def test_a_mutant_fails_its_named_test(name: str, tmp_path: Path) -> None:
    _assert_named_mutant_fails(name, tmp_path)


RAW_FINGERPRINT = Mutant(
    "identity = fingerprint(identity_text.lower(), masker.identity_key)",
    "identity = sql.lower()",
    "",
    "",
    "engine/sqltext/__init__.py",
)


def test_an_id_only_leak_fails_the_gate(tmp_path: Path) -> None:
    """The plant keeps ``sql`` safe and leaks only the fingerprint, which no gate over one text can see."""
    pytest.importorskip("sqlalchemy")  # the two target files skip without it, and pytest then finds no such test
    _mutate(_scratch_copy(tmp_path), RAW_FINGERPRINT)
    env = {**os.environ, "PYTHONPATH": str(tmp_path / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", "--tb=line",
         "-o", f"pythonpath={tmp_path / 'src'}",
         "tests/masking/a10/test_recorder.py::test_keyed_sqlite_recorder_identity_cannot_contain_a_hidden_name"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False, timeout=100,
    )  # fmt: skip
    assert done.returncode == 1, done.stdout[-2000:]
    failed = {line.split("::", 1)[1].split(" - ")[0] for line in done.stdout.splitlines() if line.startswith("FAILED")}
    assert failed == {"test_keyed_sqlite_recorder_identity_cannot_contain_a_hidden_name"}, done.stdout[-2000:]
    assert "A10SECRET" in done.stdout, done.stdout[-2000:]


@pytest.mark.parametrize("name", MUTANTS)
def test_every_lexer_branch_is_killed(name: str, tmp_path: Path) -> None:
    if name in {
        "array_space",
        "bracket_digit_word",
        "open_bracket",
        "mysql_doubled_bracket",
        "dollar_cut",
        "cut_open_double_quote",
        "double_quote_secret",
        "double_quoted_kind",
        "nested_comment",
        "bracket_opener",
    }:
        _assert_named_mutant_fails(name, tmp_path)
        return
    mutant = MUTANTS[name]
    base, mutated = _kill(mutant, tmp_path)
    print(f"mutant {name}: {mutant.gate} gate, {base} failing rows unmutated, {mutated} mutated")
    assert mutated > base, f"{name} survives: {mutant.gate} gate {base} rows unmutated, {mutated} mutated"


@pytest.mark.parametrize(
    ("name", "witness"),
    (
        ("family_cut", "dollar"),
        ("family_second_read", "dollar"),
        ("family_head", "head"),
        ("family_session", "session"),
        ("mysql_m_bang_rule", "m_bang"),
        ("mysql_t_bang_rule", "tidb"),
        ("mysql_bracket_rule", "bracket"),
        ("mariadb_backslash", "escape"),
        ("mysql_real_dollar", "real_dollar"),
        ("mysql_bad_exponent", "bad_exponent"),
        ("mysql_signed_exponent", "signed_exponent"),
        ("mysql_double_quoted_key", "key"),
        ("mysql_system_variable", "system_variable"),
    ),
)
@pytest.mark.parametrize("seed", (7, 8, 9))
def test_each_mysql_family_cut_mutant_dies_at_seeds(name: str, witness: str, seed: int, tmp_path: Path) -> None:
    _mutate(_scratch_copy(tmp_path), NAMED_MUTANTS[name])
    env = {**os.environ, "PYTHONPATH": str(tmp_path / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    node = f"tests/engine/sqltext/test_rules_mysql_family.py::test_family_cut_witness[{seed}-{witness}]"
    done = subprocess.run(
        [sys.executable, "-m", "pytest", node, "-q", "-p", "no:cacheprovider", "-p", "no:xdist"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=100,
    )
    assert done.returncode == 1, f"{name} survives seed {seed}: {done.stdout[-1500:]}"
    assert not CRASH.search(done.stdout), f"{name} crashed seed {seed}: {done.stdout[-1500:]}"


def _files_run_by(*calls: Callable[[], object]) -> set[Path]:
    """The source files whose code runs during ``calls``: what the entry points really execute."""
    package = Path(sqltrace.__file__).resolve().parents[2]
    seen: set[str] = set()

    def profile(frame: types.FrameType, event: str, _arg: object) -> None:
        if event == "call":
            seen.add(frame.f_code.co_filename)

    sys.setprofile(profile)
    try:
        for call in calls:
            call()
    finally:
        sys.setprofile(None)
    return {Path(name).resolve().relative_to(package) for name in seen if Path(name).resolve().is_relative_to(package)}


ALL_MUTANTS = {**MUTANTS, **NAMED_MUTANTS, "raw_fingerprint": RAW_FINGERPRINT}
RULE_TABLE = Path("engine/sqltext/rules.py")
# a name, a character ``[``, a comment and a placeholder: each is a rule-table mutant's branch on PostgreSQL
RULE_PROBE = "select [a], 'b' /* c */, $1 from t"


def _rule_fields_read(text: str) -> set[str]:
    """The ``POSTGRESQL`` fields a scan of ``text`` reads: a table of constants has no frame for a profile to see."""
    read: set[str] = set()

    class Recording(rule_table.LexRules):
        __slots__ = ()

        def __getattribute__(self, name: str) -> object:
            read.add(name)
            return super().__getattribute__(name)

    recording = Recording(**{f.name: getattr(rule_table.POSTGRESQL, f.name) for f in fields(rule_table.LexRules)})
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(rule_table.READINGS, Dialect.POSTGRESQL, (recording,))  # pyright: ignore[reportArgumentType]
        sqlscan.read_statement(text, Dialect.POSTGRESQL)
    return read


def _rule_field(mutant: Mutant) -> str:
    """The field a rule-table mutant changes: its anchor starts ``<field>=``."""
    return mutant.anchor.splitlines()[-1].split("=", 1)[0].strip()


def test_a_rule_mutant_counts_only_when_its_field_is_read() -> None:
    """``dollar_closer`` is read only past an opened tag, and the probe has none: a mutant of it would prove nothing."""
    unread = Mutant("dollar_closer=DollarCloser.FIRST_IDENTICAL,", "", "", "", str(RULE_TABLE))
    assert _rule_field(unread) not in _rule_fields_read(RULE_PROBE)


@pytest.mark.parametrize("name", ALL_MUTANTS)
def test_every_mutant_targets_the_module_in_use(name: str, tmp_path: Path) -> None:
    """A mutant applied to a file the entry points never run proves nothing: ``sqlscan.py`` forwards since Task 11."""
    masker = Masker(Exposure.MASKED, True)
    text = "select \"a\", 'b' from t where c in (7, ?) -- d"  # a closed name, a literal, an IN list and a comment
    package = Path(sqltrace.__file__).resolve().parents[2]
    ran = _files_run_by(
        lambda: sqlscan.read_statement(text, Dialect.MYSQL_FAMILY),
        lambda: sqlscan.shown(text, [(7, 10)], Dialect.MYSQL_FAMILY),
        lambda: statement_text(masker, text, Dialect.MYSQL_FAMILY),
        lambda: sqltext.statement_shape(masker, text, Dialect.MYSQL_FAMILY),
        lambda: render_error(masker, f"(pymysql.err.Error) x\n[SQL: {text}]", Dialect.MYSQL_FAMILY),  # the driver line
    )  # fmt: skip

    written = _mutate(_scratch_copy(tmp_path), ALL_MUTANTS[name]).relative_to(tmp_path / "src" / "sharpit")

    if written == RULE_TABLE:
        field = _rule_field(ALL_MUTANTS[name])
        if ALL_MUTANTS[name].anchor != "backslash_token=True,":  # a `\\` reads it, and the probe holds none
            assert field in _rule_fields_read(RULE_PROBE), f"{name} changes {field}: no scan of the probe reads it"
    else:
        assert written in ran, f"{name} writes {written}: no entry point runs it"
    assert (package / written).is_file()
