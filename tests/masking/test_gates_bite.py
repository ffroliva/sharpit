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
from pathlib import Path
from typing import NamedTuple

import pytest
from tests.masking import mutant_worker, sql_corpus
from tests.masking import test_statement_surfaces as gates

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
    module: str = ""  # a path under the package, when the mutant is not in the lexer


LEXER_MODULE = "sharpit.engine.sqltext.lexer"  # where a mutant lands unless it names a module
RENDER = "engine/sqltext/render.py"
FACADE = "engine/capture/sqlscan.py"
KEEP = "return _keep(source, index, out)"
DOT_DIGIT = ' or out.chars[-1] == "."'
DIGIT = f"elif c.isdigit() and (not _identifier_char_before(out){DOT_DIGIT}):"
QUOTES = "**dict.fromkeys('\"`[', _scan_quoted),"  # the scanners of the three quoting characters
CUT = "found = _RUN_OPENER.search(scan.source)"
TIGHT = '_TIGHT_DASH_OPENER = re.compile(rf"{_RUN_OPENER.pattern}|/\\*")'
NO_DOLLAR = 're.compile("[\'\\"`]")'  # the opener set without its dollar quote
MYSQL_TAG = "rules.dollar is DollarOpen.MYSQL_TAG"
CLOSER = "_no_step_back_closer(sql, tag, body_start) if no_step_back else sql.find(tag, body_start)"
DRIVER_SWITCH = Mutant(
    "self.driver = self.driver or (Dialect.MYSQL_FAMILY if named else None)",
    "self.driver = None",
    "",
    "",
    "engine/capture/errortext.py",
)
# the seeded rows hold no quote before a ``#`` (0 failing rows mutated or not at 300): F1's own rows see it
HASH_CUT_BEFORE_OPENER = Mutant(
    'if rules.hash is HashRule.CUT and cut >= 0 and source[cut] == "#":', "if False:", "", ""
)
MUTANTS: dict[str, Mutant] = {
    "true": Mutant("return index + 4, True", KEEP, SURFACE, "visible"),
    "false": Mutant("return index + 5, True", KEEP, SURFACE, "visible"),
    "exponent": Mutant("return _skip_exponent(sql, cursor)", "return cursor", SURFACE, "shape"),
    "exponent_sign": Mutant('if cursor < length and sql[cursor] in "+-":', "if False:", SURFACE, "shape"),
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
                          "subscript = subscript or False", "recorder_sql-generic", "shape"),
    # a name holding a quote is plain only on MySQL (r6): generic, a cut hides what follows it anyway
    "backtick": Mutant(QUOTES, QUOTES.replace("`", ""), "recorder_sql-mysql", "visible"),
    "bracket": Mutant(QUOTES, QUOTES.replace("[", ""), SURFACE, "shape"),
    "hash": Mutant('(rules.hash is HashRule.COMMENT and sql[index] == "#")', "False", "db_statement-mysql", "visible"),
    "dollar": Mutant("return (end, True) if end > 0 else " + KEEP[7:], KEEP, SURFACE, "visible"),
    "unclosed_dollar": Mutant("return length if end < 0 else end + len(tag)",
                              "return -1 if end < 0 else end + len(tag)", SURFACE, "visible"),
    "leading_dot": Mutant('".": _scan_dot,', "", SURFACE, "shape"),  # the digits hide anyway since r8: it shows ``.?``
    "radix": Mutant('if sql[index] == "0" and (radix', "if False and (radix", SURFACE, "visible"),
    "underscore": Mutant('or (sql[cursor] == "_" and sql[cursor + 1 : cursor + 2].isdigit())', "", SURFACE, "visible"),
    "open_bracket": Mutant("if not runs or runs[-1][1] != end - index:", "if True:", "recorder_sql-generic", "visible"),
    "bracket_opener": Mutant("for stop in (found, _bracket_opener(scan)) if stop", "for stop in (found,) if stop",
                             "recorder_sql-generic", "visible"),
    "executable_comment": Mutant(
        "return source.startswith(tuple(rules.executable_prefixes), start)",
        "return False",
        "recorder_sql-mysql",
        "visible",
    ),
    "tight_backtick": Mutant(TIGHT, TIGHT.replace("_RUN_OPENER.pattern", '_RUN_OPENER.pattern.replace("`", "")'),
                             "recorder_sql-generic", "visible"),
    "tight_block_comment": Mutant(TIGHT, "_TIGHT_DASH_OPENER = _RUN_OPENER", "recorder_sql-generic", "visible"),
    "backtick_cut": Mutant(CUT, "found = _QUOTE.search(scan.source)", "recorder_sql-generic", "visible"),
    "backtick_cut_mysql": Mutant(CUT, "found = _QUOTE.search(scan.source)", "recorder_sql-mysql", "visible"),
    "dollar_cut": Mutant(CUT, f"found = {NO_DOLLAR}.search(scan.source)", "recorder_sql-generic", "visible"),
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
    "family_cut": Mutant(f"return _family_cut(scan, rules) if {MYSQL_TAG} else -1", "return -1", "recorder_sql-mysql",
                         "visible"),
    "family_second_read": Mutant("scanners = _SCANNERS if dollar else _NO_DOLLAR_SCANNERS", "scanners = _SCANNERS",
                                 "recorder_sql-mysql", "visible"),
    "number_dollar": Mutant('last == "?" and source[index - 1].isalnum()', "False", "recorder_sql-generic", "visible"),
    "dot_opens": Mutant('or last in "_$" or', 'or last in "_$." or', "recorder_sql-generic", "visible"),
    "backtick_quote": Mutant("if rules.backtick_run is BacktickRun.NAME_OR_CUT and _backtick_reads_two_ways(",
                             "if False and _backtick_reads_two_ways(", "recorder_sql-generic", "visible"),
    "unclosed_backtick": Mutant(' or source.count("`", start, end) % 2', "", "recorder_sql-generic", "visible"),
    "at_dollar_cut": Mutant('if source.startswith("@$", end - 1):', "if False:", "recorder_sql-generic", "visible"),
    "dot_dollar_cut": Mutant('if source.startswith(".$", end - 1) and', "if False and", "recorder_sql-generic",
                             "visible"),
    "dot_dollar_tail": Mutant(" or _OPENER.search(source, end))", ")", "recorder_sql-generic", "visible"),
    "dot_dollar_body": Mutant("_OPENER.search(source, start + tag, end - tag) or ", "", "recorder_sql-generic",
                              "visible"),
    "dot_dollar_holds": Mutant(' or ".$" in source', "", "recorder_sql-generic", "visible"),
    "bracket_digit_word": Mutant(r'(?: +[^\W\d]\w*)* *\]")', r'[\w ]*\]")', SURFACE, "visible"),
    "cut_open_double_quote": Mutant("if string or end >= _MAX_SCAN_LENGTH:", "if string:", SURFACE, "visible"),
    "two_readings": Mutant("return _read(source.replace(", "return False and _read(source.replace(",
                           SURFACE, "visible"),
    "nested_comment": Mutant(
        'if rules.nested_comments is Reading.CUT and source.find("/*", start + 2, end) >= 0:',
        "if False:",
        SURFACE,
        "visible",
    ),
    "alternative_quote": Mutant("if _ALTERNATIVE_QUOTE.search(source, start, end + 1):", "if False:",
                                SURFACE, "visible"),
    # a digit or a keyword after a name character belongs to the name: over-masking ``col1`` lowers A1: A3 must catch it
    "digit_in_name": Mutant(DIGIT, "elif c.isdigit():", SURFACE, "shape"),
    "dot_digit": Mutant(DIGIT, DIGIT.replace(DOT_DIGIT, ""), SURFACE, "visible"),
    "dot_digit_mysql": Mutant(DIGIT, DIGIT.replace(DOT_DIGIT, ""), "recorder_sql-mysql", "visible"),
    # as ``mysql_dollar_name``: the ``$`` they free opens a quote, and the family cut stops there
    "name_part": Mutant("_skip_number(source, index, _name_part(out))", "_skip_number(source, index)",
                        "recorder_sql-mysql", "shape"),
    "at_token": Mutant("if not rules.at_token or found is None:", "if True:", "recorder_sql-mysql", "shape"),
    "at_number": Mutant("if _AT_NUMBER.search(found[0]):", "if False:", "db_statement-mysql", "shape"),
    "release_name": Mutant('if flags[literal] and literal > start and source[literal - 1] == "=":', "if False:",
                           "db_statement-mysql", "shape", RENDER),
    "verb_lookahead": Mutant(r"(?=[^\w$-]|$)", r"(?=[\s(;]|$)", "db_statement-generic", "shape",
                             "engine/capture/statement.py"),
    "keyword_in_name": Mutant(
        "if _identifier_char_before(out):\n        return _keep(source, index, out)",
        "if False:\n        return _keep(source, index, out)",
        SURFACE,
        "shape",
    ),
    "ascii_space": Mutant("elif c in _SPACE:", "elif c.isspace():", SURFACE, "visible"),
    "ascii_space_collapse": Mutant("if c in _SPACE and collapse:", "if c.isspace() and collapse:", SURFACE, "shape",
                                   RENDER),
    "in_collapse": Mutant("if _PLACEHOLDER_RUN.search(normalized) is None:", "if True:", SURFACE, "shape", RENDER),
    # also dies on every surface's ``shape``: a masker hides the token as a mask where the scan left ``?``, so only the
    # scan alone shows it as ``visible``. Its one visible job in production is METADATA_ONLY, where no masker reads
    "double_quote_secret": Mutant("return is_secret_value(body)", "return False", "scan_alone-generic", "visible",
                                  FACADE),
    # the lexer's hand-over: a ``"`` run it cannot place is a name to the renderer to judge, not code to copy at once
    "double_quoted_kind": Mutant("        return True\n    return None\n", "        return True\n    return False\n",
                                 "scan_alone-generic", "visible"),
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
    "scan_alone-generic",
    "shape",
)  # the predicate count is no gate's row: only the lexer's own test sees it
CLOSER_DIALECT = Mutant(
    "_read(text[:_MAX_SCAN_LENGTH], readings(dialect)[0]), text)",
    "_read(text[:_MAX_SCAN_LENGTH], GENERIC), text)",
    "scan_alone-generic",
    "shape",
)  # no row reads a ``[SQL: `` block: only the lexer's own test sees which dialect ``block_closer`` is given
TWO_WAYS_DIALECT = Mutant(
    "rules = readings(dialect)[0]",
    "rules = GENERIC",
    "scan_alone-generic",
    "shape",
)  # likewise for ``reads_two_ways``
GENERIC_HASH_STOPS = Mutant(
    'if rules.hash is HashRule.CUT and source[index] == "#":', "if False:", "scan_alone-generic", "shape"
)
GENERIC_HASH_ADDS_NO_VALUE = Mutant(
    'if rules.hash is HashRule.CUT and source[cut] == "#":', "if False:", "scan_alone-generic", "shape"
)
GENERIC_HASH_IS_A_GUESS = Mutant(
    "hash_cut = rules.hash is HashRule.CUT and scan.cut >= 0", "hash_cut = False", "scan_alone-generic", "shape"
)
TOKEN_GATE_SKIPS_ALL = Mutant("if _SECRET_HINT.search(tracked.text):", "if False:", "", "", "engine/masking.py")
TOKEN_GATE_SKIPS_EACH = Mutant("if _SECRET_HINT.search(token) is None:", "if True:", "", "", "engine/masking.py")
TOKEN_GATE_TEST = "tests/engine/test_masking_token_gate.py::test_a_secret_the_gate_could_miss_is_still_masked"
# each field gates its own cut: with it read away MySQL text stops where only generic text stops, and no row holds that
CR_CUT_FIELD = Mutant('if rules.cr_ends_dash is Reading.CUT and "\\r" in', 'if "\\r" in', "scan_alone-generic", "shape")
DASH_CUT_FIELD = Mutant(
    "return rules.dash_needs_space is Reading.CUT and tight and", "return tight and", "scan_alone-generic", "shape"
)
RENDER_PREDICATE = Mutant(
    "predicates += candidate.predicate", "predicates += False", "scan_alone-generic", "shape", RENDER
)
SQLITE_DOUBLE_QUOTE = Mutant("if scan.hide_double_quoted:", "if False:", "scan_alone-generic", "shape", RENDER)
SQLITE_SUFFIX = Mutant('elif c == "(":', "elif False:", "scan_alone-generic", "shape")
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
PG_CUT_BACKSLASH = Mutant("if rules.cut_backslash and _backslash_reads_two_ways(scan, rules):", "if False:", "", "")
PG_ESCAPES_IN_QUOTED_E = Mutant(
    'if rules.backslash_in_single is Backslash.E_ONLY:\n        prefix = index > 0 and sql[index - 1] in "eE"',
    'if False:\n        prefix = index > 0 and sql[index - 1] in "eE"',
    "",
    "",
)
PG_BACKSLASH_TWO_WAYS_E = Mutant(
    "if rules.backslash_in_single is Backslash.E_ONLY:\n"
    "        return _read(source, replace(rules, backslash_in_single=Backslash.ALWAYS)).out.text() != scan.out.text()",
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
PG_QUOTED_NAME_BACKSLASH_CUT = Mutant(
    "and rules.double_quote is not DoubleQuote.NAME",
    "and True",
    "",
    "",
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
    'if cursor == length or source[cursor] != ")":\n            return index, True',
    'if cursor == length or source[cursor] != ")":\n            return cursor, False',
    "",
    "",
)
SQLITE_QUOTED_SUFFIX = Mutant(
    """if "'" in source[opening:cursor] or '"' in source[opening:cursor]:""",
    "if False:",
    "",
    "",
)
SQLITE_DOUBLE_QUOTED_SUFFIX = Mutant(
    """if "'" in source[opening:cursor] or '"' in source[opening:cursor]:""",
    """if "'" in source[opening:cursor]:""",
    "",
    "",
)
SQLITE_CUT_IS_A_GUESS = Mutant(
    "variable_cut = rules.variable_suffix is VariableSuffix.TCL_PAREN and scan.cut >= 0",
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
MYSQL_M_BANG_CUT = Mutant(
    "return source.startswith(tuple(rules.executable_prefixes), start)",
    'return source.startswith(("/*!",), start)',
    "",
    "visible",
)
NAMED_MUTANTS = {
    "token_gate_skips_all": TOKEN_GATE_SKIPS_ALL,
    "token_gate_skips_each": TOKEN_GATE_SKIPS_EACH,
    "generic_hash_stops": GENERIC_HASH_STOPS,
    "generic_hash_adds_no_value": GENERIC_HASH_ADDS_NO_VALUE,
    "generic_hash_is_a_guess": GENERIC_HASH_IS_A_GUESS,
    "mysql_closer_never": NEVER_CLOSES,
    "mysql_closer": MUTANTS["mysql_closer"],
    "mysql_driver_switch": DRIVER_SWITCH,
    "hash_cut_before_opener": HASH_CUT_BEFORE_OPENER,
    "candidate_predicate": CANDIDATE_PREDICATE,
    "closer_dialect": CLOSER_DIALECT,
    "two_ways_dialect": TWO_WAYS_DIALECT,
    "render_predicate": RENDER_PREDICATE,
    "cr_cut_field": CR_CUT_FIELD,
    "dash_cut_field": DASH_CUT_FIELD,
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
    "pg_quoted_name_backslash_cut": PG_QUOTED_NAME_BACKSLASH_CUT,
    "pg_first_line_ending": PG_FIRST_LINE_ENDING,
    "mysql_bracket_cut": MYSQL_BRACKET_CUT,
    "mysql_nested_comment_cut": MYSQL_NESTED_COMMENT_CUT,
    "mysql_m_bang_cut": MYSQL_M_BANG_CUT,
}
CLOSED_QUOTE = "tests/engine/sqltext/test_lexer.py::test_mysql_dollar_closer_does_not_step_back_after_a_partial_match"
PREDICATE = (
    "tests/engine/sqltext/test_lexer.py::test_a_candidate_remembers_whether_a_literal_there_would_sit_in_a_predicate"
)
NAMED_TESTS = {
    "token_gate_skips_all": TOKEN_GATE_TEST,
    "token_gate_skips_each": TOKEN_GATE_TEST,
    "generic_hash_stops": "tests/engine/sqltext/test_lexer.py::test_generic_hides_everything_past_a_hash",
    "generic_hash_adds_no_value": "tests/engine/sqltext/test_lexer.py::test_generic_hides_everything_past_a_hash",
    "generic_hash_is_a_guess": "tests/engine/sqltext/test_lexer.py::test_a_closer_past_a_generic_hash_is_a_guess",
    "mysql_closer_never": CLOSED_QUOTE,
    "mysql_closer": CLOSED_QUOTE,
    "mysql_driver_switch": "tests/masking/test_error_regions.py::test_a_driver_line_does_switch_mysql_mode",
    "hash_cut_before_opener": (
        "tests/engine/capture/test_statement.py::test_unsupported_hash_cut_hides_the_first_opener"
    ),
    "candidate_predicate": PREDICATE,
    "closer_dialect": "tests/engine/sqltext/test_lexer.py::test_block_closer_reads_the_dialect_it_is_given",
    "two_ways_dialect": "tests/engine/sqltext/test_lexer.py::test_reads_two_ways_reads_the_dialect_it_is_given",
    "render_predicate": "tests/engine/sqltext/test_render.py::test_a_secret_run_in_a_predicate_is_a_predicate_literal",
    "cr_cut_field": "tests/engine/sqltext/test_lexer.py::test_a_lone_cr_in_a_comment_cuts_only_generic_text",
    "dash_cut_field": "tests/engine/sqltext/test_lexer.py::test_an_opener_in_a_tight_comment_cuts_only_generic_text",
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
    "pg_quoted_name_backslash_cut": (
        "tests/engine/sqltext/test_rules_postgresql.py::test_a_backslash_in_a_postgresql_quoted_name_does_not_cut"
    ),
    "pg_first_line_ending": "tests/engine/sqltext/test_rules_postgresql.py::test_line_comment_ends_at_cr_or_lf",
    "mysql_bracket_cut": "tests/engine/capture/test_sqlscan.py::test_the_other_cuts_stand_on_a_text_holding_a_dollar",
    "mysql_nested_comment_cut": (
        "tests/engine/capture/test_sqlscan.py::test_a_nested_comment_and_a_differing_backslash_cut_on_mysql"
    ),
    "mysql_m_bang_cut": (
        "tests/engine/capture/test_sqlscan.py::test_an_executable_comment_ends_later_than_the_scan_reads"
    ),
}


CRASH = re.compile(r"\b(?:UnboundLocal|Name|Attribute|Type|Syntax|Index|Key)Error\b")  # a crash is not a red


@pytest.mark.parametrize("name", NAMED_TESTS)
def test_a_mutant_fails_its_named_test(name: str, tmp_path: Path) -> None:
    copy = _scratch_copy(tmp_path)
    _mutate(copy, NAMED_MUTANTS[name])
    env = {**os.environ, "PYTHONPATH": str(tmp_path / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run(
        [sys.executable, "-m", "pytest", NAMED_TESTS[name], "-q", "-p", "no:cacheprovider", "-p", "no:xdist"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False, timeout=100,
    )  # fmt: skip
    assert done.returncode == 1, f"{name} survives its named test: {done.stdout[-1500:]}"
    assert not CRASH.search(done.stdout), f"{name} crashed its test, which proves nothing: {done.stdout[-1500:]}"


RAW_FINGERPRINT = Mutant(
    "identity = text.lower() if text is not None else reading.shape.fingerprint",
    "identity = reading.shape.fingerprint",
    "",
    "",
    "engine/capture/statement.py",
)


def test_an_id_only_leak_fails_the_gate(tmp_path: Path) -> None:
    """The plant keeps ``sql`` safe and leaks only the fingerprint, which no gate over one text can see."""
    pytest.importorskip("sqlalchemy")  # the two target files skip without it, and pytest then finds no such test
    _mutate(_scratch_copy(tmp_path), RAW_FINGERPRINT)
    env = {**os.environ, "PYTHONPATH": str(tmp_path / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", "--tb=line",
         "tests/masking/test_serialized_reports.py::test_no_secret_in_test_session_facts",
         "tests/masking/test_serialized_reports.py::test_no_secret_in_a_relationship_group"],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False, timeout=100,
    )  # fmt: skip
    assert done.returncode == 1, done.stdout[-2000:]
    failed = {line.split("::", 1)[1].split(" - ")[0] for line in done.stdout.splitlines() if line.startswith("FAILED")}
    assert "test_no_secret_in_test_session_facts[unquoted_alias-attributed]" in failed, done.stdout[-2000:]
    assert "test_no_secret_in_a_relationship_group[upper_case_alias]" in failed, done.stdout[-2000:]
    assert "AssertionError" in done.stdout, done.stdout[-2000:]  # the gate's own assertion, no crash


@pytest.mark.parametrize("name", MUTANTS)
def test_every_lexer_branch_is_killed(name: str, tmp_path: Path) -> None:
    mutant = MUTANTS[name]
    base, mutated = _kill(mutant, tmp_path)
    print(f"mutant {name}: {mutant.gate} gate, {base} failing rows unmutated, {mutated} mutated")
    if mutated <= base:
        raise SurvivedMutant(f"{name} survives: {mutant.gate} gate {base} rows unmutated, {mutated} mutated")


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
    return mutant.anchor.split("=", 1)[0]


def test_a_rule_mutant_counts_only_when_its_field_is_read() -> None:
    """``dollar_closer`` is read only past an opened tag, and the probe has none: a mutant of it would prove nothing."""
    unread = Mutant("dollar_closer=DollarCloser.FIRST_IDENTICAL,", "", "", "", str(RULE_TABLE))
    assert _rule_field(unread) not in _rule_fields_read(RULE_PROBE)


@pytest.mark.parametrize("name", ALL_MUTANTS)
def test_every_mutant_targets_the_module_in_use(name: str, tmp_path: Path) -> None:
    """A mutant applied to a file the entry points never run proves nothing: ``sqlscan.py`` forwards since Task 11."""
    masker = Masker(Exposure.MASKED, True)
    text = "select \"a\", 'b' from t where c in (?, ?) -- d"  # a closed name, a literal, an IN list and a comment
    package = Path(sqltrace.__file__).resolve().parents[2]
    ran = _files_run_by(
        lambda: sqlscan.read_statement(text, Dialect.UNSUPPORTED),
        lambda: sqlscan.shown(text, [(7, 10)], Dialect.UNSUPPORTED),
        lambda: statement_text(masker, text, Dialect.UNSUPPORTED),
        lambda: render_error(masker, f"(pymysql.err.Error) x\n[SQL: {text}]", Dialect.UNSUPPORTED),  # the driver line
    )  # fmt: skip

    written = _mutate(_scratch_copy(tmp_path), ALL_MUTANTS[name]).relative_to(tmp_path / "src" / "sharpit")

    if written == RULE_TABLE:
        field = _rule_field(ALL_MUTANTS[name])
        assert field in _rule_fields_read(RULE_PROBE), f"{name} changes {field}: no scan of the probe reads it"
    else:
        assert written in ran, f"{name} writes {written}: no entry point runs it"
    assert (package / written).is_file()
