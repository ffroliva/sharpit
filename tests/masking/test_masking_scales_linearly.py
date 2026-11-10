"""Class gate: masking holds the GIL, so a superlinear pass on a client-sized value freezes the host.

Each doubling must cost less than 3 times the last, and 32 KB under a second. This measures CPU time, which a busy
machine does not inflate: the minimum of a few repeats, re-measured when a step fails, a floor under millisecond noise.
A new heuristic only has to survive these generators to ship; add the input that broke it here.
"""

from __future__ import annotations

import gc
import sys
import time
from collections.abc import Callable
from functools import partial

import pytest

from sharpit.engine import masking, sqltext
from sharpit.engine.capture.sqlscan import normalize, shown
from sharpit.engine.capture.sqltrace import mask_error
from sharpit.engine.capture.statement import statement_text
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import Dialect, read_chain, render

MASKER = Masker(Exposure.MASKED, True)
SIZES = (4_000, 8_000, 16_000, 32_000)
SCAN_SIZES = (5_000, 10_000, 19_900)  # past the scan's limit of 20,000 a step is flat by construction
REPEATS = 3
ATTEMPTS = 3
MAX_STEP = 3
MAX_SECONDS = 1
MIN_SAMPLE_SECONDS = 0.05
FLOOR_SECONDS = 0.001  # below this a ratio is scheduler noise
ESCAPED_QUOTE = '\\"'


def _repeat(unit: str) -> Callable[[int], str]:
    return lambda size: unit * (size // len(unit))


GENERATORS: dict[str, Callable[[int], str]] = {
    "quote-run": lambda size: "token " + '"' * size + "1",
    "quote-pairs": _repeat("\"' "),
    # the count is fixed even or odd: the body read cuts on an open run, so a parity that flips between sizes compares
    # a full read with a cut, and that step is not the scan's growth
    "escaped-quote-run": lambda size: "password=[" + ESCAPED_QUOTE * (size // 4 * 2) + "]",
    "escaped-quote-run-odd": lambda size: "password=[" + ESCAPED_QUOTE * (size // 4 * 2 + 1) + "]",
    "escaped-quote-pairs": _repeat(f'"k":"{ESCAPED_QUOTE}'),
    "bracket-run": lambda size: "password=" + "[" * size,
    "unclosed-brackets": _repeat("k=[ "),
    "unclosed-parens": _repeat('"k":( '),
    "nested-brackets": _repeat("password=[[] "),
    "closers": lambda size: ")" * size + "a",
    "sql-block-run": _repeat("[SQL: "),
    "sql-line-run": _repeat("\n[SQL: "),
    "sql-subscripts": _repeat("[SQL: a[1] "),
    "secret-keys": _repeat("password="),
    "secret-pairs": _repeat("password=a "),
    "secret-lines": _repeat("token: a\n"),
    "bearer-chain": _repeat("bearer token "),
    "jwt-prefix": _repeat("eyJ"),
    "pem-prefix": _repeat("=BEGIN "),
    "mixed": _repeat('"k":[ \\" [SQL: eyJ BEGIN token "1 '),
    # a quoted name is the one place the scan's output keeps a run of spaces
    "quoted-name-spaces": lambda size: "SELECT 1, `" + " " * size + "`",
    "quoted-name-list": lambda size: "SELECT ?, `" + " " * (size // 2) + "(" + "," * (size // 2) + "`",
    "quoted-name-row": lambda size: "VALUES `)" + " " * (size // 2) + ",(`" + ', "a"' * (size // 10),
    # what the ambiguity check reads: a run for each, and a trigger that is checked at every position
    "odd-quote-brackets": _repeat("['] "),
    "open-odd-quote-brackets": _repeat("[' "),
    "escaped-quotes": _repeat("a\\'b "),
    "nested-comments": _repeat("/* /* */ '' "),
    "alternative-quotes": _repeat("q'a' "),
    "hash-quotes": _repeat("# 'a' "),
    "hash-numbers": _repeat("# 1 "),  # a span for each number, and no quote to find after any ``#``
    "backtick-brackets": _repeat("[`] "),
    # each body opens a run with no closer in the text: only the bound on the body keeps these linear
    "dollar-brackets": _repeat("[$a$] "),
    "comment-brackets": _repeat("[/*] "),
    "dash-brackets": _repeat("[-- ] "),
    "open-run-brackets": _repeat("[/* ["),
    "open-word-bracket": lambda size: "k=[" + "a " * (size // 2),  # the name read fails only at the end, once
    "word-brackets": _repeat("[a 1 "),
    "dollar-openers": _repeat("# $a$ $1 "),  # the last opener is found once, not per ``#``
    "closed-run-brackets": _repeat("['a'] "),
    "subscripts": _repeat("a['] "),
    "at-dollars": _repeat("@$$ $$ "),
    "lone-crs": _repeat("-- a\r'\n"),
    "open-double-quote": lambda size: "SELECT " + "a, " * (size // 3) + '"' + "y" * 30_000,
    # the closer: 500 to 4,000 ``]\n[SQL: `` pairs over ``SIZES``, bare and inside an error's block
    "closer-pairs": _repeat("]\n[SQL: "),
    "closer-pairs-in-block": lambda size: "(psycopg.ProgrammingError) x\n[SQL: " + "]\n[SQL: " * (size // 8),
    # the region renderer: a traceback of many frames, then the block it fails on
    "many-frames": lambda size: (
        "Traceback (most recent call last):\n"
        + '  File "/srv/app/db.py", line 12, in run\n    conn.execute(q)\n' * (size // 60)
        + "sqlalchemy.exc.ProgrammingError: (psycopg.ProgrammingError) x\n[SQL: SELECT 'a']\n[parameters: (1,)]"
    ),
}


def _pair_substitution(text: str) -> str:
    tracked = masking.Tracked(text)
    masking._mask_pairs(masking._TEXT_QUOTED_PAIR, masking._QUOTED_PAIR_MASKED, tracked)  # noqa: SLF001
    masking._mask_pairs(masking._TEXT_PAIR, masking._PAIR_MASKED, tracked)  # noqa: SLF001
    return tracked.text


Entry = Callable[[str], object]
ENTRY_POINTS: dict[str, Entry] = {
    "mask_text": MASKER.mask_text,
    "mask_error": lambda text: mask_error(MASKER, text, Dialect.POSTGRESQL),
    "pair_substitution": _pair_substitution,
    "mask_spans": MASKER.mask_spans,
    "mask_spans_relaxed": lambda text: MASKER.mask_spans(text, strict=False),
    "mask_statement": MASKER.mask_statement,
    "statement_text": lambda text: statement_text(MASKER, text, Dialect.POSTGRESQL),
    "facade_statement_text": lambda text: sqltext.statement_text(MASKER, text, Dialect.POSTGRESQL),
    "statement_shape": lambda text: sqltext.statement_shape(MASKER, text, Dialect.POSTGRESQL),
    "error_text": lambda text: sqltext.error_text(MASKER, text, Dialect.POSTGRESQL, known=True),
    "error_text_free": lambda text: sqltext.error_text(MASKER, text, Dialect.POSTGRESQL),
    "closer": lambda text: sqltext.LEXER.block_closer(text, Dialect.POSTGRESQL),
}


def _overlapping(size: int) -> list[tuple[int, int]]:
    return [(start, size) for start in range(size)]


def _shown_at(size: int) -> Entry:
    spans = _overlapping(size)  # outside the timer: the entry is measured, not the list a caller already holds
    return lambda text: shown(text, spans, Dialect.POSTGRESQL)


def _flags_at(size: int) -> Entry:
    spans = _overlapping(size)
    return lambda text: render._hidden_flags(spans, len(text))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


_NORMALIZE = partial(normalize, dialect=Dialect.POSTGRESQL)
SCAN_ENTRY_POINTS: dict[str, Callable[[int], Entry]] = {"normalize": lambda _size: _NORMALIZE, "shown": _shown_at}


def _seconds(entry: Entry, text: str) -> float:
    best = float("inf")
    for repeat in range(REPEATS):
        runs = 0
        started = time.process_time()
        while (spent := time.process_time() - started) < MIN_SAMPLE_SECONDS:  # the clock ticks every 15.6 ms on Windows
            runs += 1
            entry(f"{text} {repeat} {runs}")  # unique: past the normaliser's cache
        best = min(best, spent / runs)
    return best


def _step(
    entry_at: Callable[[int], Entry], make: Callable[[int], str], size: int, half: float | None = None
) -> tuple[float, float]:
    """Return the minimum ratio and full-size sample; ``half`` reuses the prior step's full-size sample."""
    half_entry, full_entry = entry_at(size // 2), entry_at(size)
    step = float("inf")
    minimum_full = float("inf")
    for attempt in range(ATTEMPTS):
        half_seconds = half if attempt == 0 and half is not None else _seconds(half_entry, make(size // 2))
        full = _seconds(full_entry, make(size))
        minimum_full = min(minimum_full, full)
        step = min(step, (full + FLOOR_SECONDS) / (half_seconds + FLOOR_SECONDS))
        if step < MAX_STEP:
            break
    return step, minimum_full


def _assert_linear(entry_at: Callable[[int], Entry], make: Callable[[int], str], sizes: tuple[int, ...]) -> None:
    assert sizes, "sizes must not be empty"
    gc_was_on = gc.isenabled()
    gc.disable()
    try:
        half = None
        previous_size = 0
        largest = 0.0
        for size in sizes:  # smallest first: a quadratic pass fails before it runs into the test timeout
            step, largest = _step(entry_at, make, size, half if size // 2 == previous_size else None)
            half = largest
            previous_size = size
            assert step < MAX_STEP, f"{size} chars cost {step:.1f}x the half size"
    finally:
        if gc_was_on:
            gc.enable()
    assert largest < MAX_SECONDS


def test_each_size_is_measured_once_per_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    measured: list[int] = []

    def seconds(_entry: Entry, text: str) -> float:
        measured.append(len(text))
        return 0.01

    monkeypatch.setattr(sys.modules[__name__], "_seconds", seconds)
    _assert_linear(lambda _size: lambda _text: None, lambda size: "x" * size, SIZES[1:])

    assert measured == list(SIZES)


def test_non_doubling_scan_step_measures_its_own_half(monkeypatch: pytest.MonkeyPatch) -> None:
    measured: list[int] = []

    def seconds(_entry: Entry, text: str) -> float:
        measured.append(len(text))
        return 0.01

    monkeypatch.setattr(sys.modules[__name__], "_seconds", seconds)
    _assert_linear(lambda _size: lambda _text: None, lambda size: "x" * size, SCAN_SIZES)

    assert measured[-2:] == [9_950, 19_900]


def test_a_retry_measures_both_sizes_fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    measured: list[int] = []
    durations = iter((0.1, 0.01, 0.01))

    def seconds(_entry: Entry, text: str) -> float:
        measured.append(len(text))
        return next(durations)

    monkeypatch.setattr(sys.modules[__name__], "_seconds", seconds)
    _step(lambda _size: lambda _text: None, lambda size: "x" * size, 1_600, half=0.01)

    assert measured == [1_600, 800, 1_600]


def test_a_planted_quadratic_entry_still_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    measured: list[int] = []

    def quadratic(text: str) -> None:
        if len(text) > 1_600:
            for _ in range(len(text)):
                for _ in range(len(text)):
                    pass

    def seconds(entry: Entry, text: str) -> float:
        measured.append(len(text))
        entry(text)
        return 0.1 if len(text) > 1_600 else 0.01

    monkeypatch.setattr(sys.modules[__name__], "_seconds", seconds)

    with pytest.raises(AssertionError, match="3200 chars cost .* the half size"):
        _assert_linear(lambda _size: quadratic, lambda size: "x" * size, (800, 1_600, 3_200))

    assert measured == [400, 800, 1_600, 3_200, 1_600, 3_200, 1_600, 3_200]


def test_retry_carries_the_minimum_full_sample_forward(monkeypatch: pytest.MonkeyPatch) -> None:
    counts: dict[int, int] = {}

    def seconds(_entry: Entry, text: str) -> float:
        size = len(text)
        counts[size] = counts.get(size, 0) + 1
        if size == 800 and counts[size] == 1:
            return 0.1
        if size == 1_600:
            return 0.04
        return 0.01

    monkeypatch.setattr(sys.modules[__name__], "_seconds", seconds)

    with pytest.raises(AssertionError, match="1600 chars cost .* the half size"):
        _assert_linear(lambda _size: lambda _text: None, lambda size: "x" * size, (400, 800, 1_600))


def test_step_rejects_empty_sizes() -> None:
    with pytest.raises(AssertionError, match="sizes"):
        _assert_linear(lambda _size: lambda _text: None, lambda size: "x" * size, ())


def test_overlapping_hidden_spans_are_written_once() -> None:
    """Direct, and far past ``SIZES``: writing a span again is a ``memset``, too cheap to see under the scan's cost."""
    _assert_linear(_flags_at, GENERATORS["closers"], (200_000,))


@pytest.mark.parametrize("entry", ENTRY_POINTS)
@pytest.mark.parametrize("generator", GENERATORS)
def test_masking_scales_linearly(entry: str, generator: str) -> None:
    run = ENTRY_POINTS[entry]
    _assert_linear(lambda _size: run, GENERATORS[generator], SIZES[1:])


def _cause_chain(size: int) -> BaseException:
    head = RuntimeError("0")
    current = head
    for index in range(1, size):
        link = RuntimeError(str(index))
        if index % 2:
            current.__cause__ = link
        else:
            current.__context__ = link
        current = link
    return head


def _wide_group(size: int) -> BaseException:
    return ExceptionGroup("wide", [RuntimeError(str(index)) for index in range(size)])


def _walk_at(build: Callable[[int], BaseException], read: Callable[[BaseException], object]) -> Callable[[int], Entry]:
    def entry_at(size: int) -> Entry:
        exc = build(size)  # outside the timer: the walk is measured, not the chain a host already raised
        return lambda _text: read(exc)

    return entry_at


def _error_text_of(exc: BaseException) -> object:
    return sqltext.error_text(MASKER, exc, Dialect.POSTGRESQL)


WALKS: dict[str, Callable[[int], Entry]] = {
    "read_chain-cause-chain": _walk_at(_cause_chain, read_chain),
    "read_chain-wide-group": _walk_at(_wide_group, read_chain),
    "exception_leaves-wide-group": _walk_at(_wide_group, sqltext.exception_leaves),
    "error_text-cause-chain": _walk_at(_cause_chain, _error_text_of),
    "error_text-wide-group": _walk_at(_wide_group, _error_text_of),
}


@pytest.mark.parametrize("walk", WALKS)
def test_the_exception_walk_scales_linearly(walk: str) -> None:
    """A long ``__cause__``/``__context__`` chain and a wide group: the walk is bounded, so each step stays flat."""
    _assert_linear(WALKS[walk], lambda _size: "", SIZES)


@pytest.mark.parametrize("entry", SCAN_ENTRY_POINTS)
@pytest.mark.parametrize("generator", GENERATORS)
def test_the_scan_scales_linearly(entry: str, generator: str) -> None:
    _assert_linear(SCAN_ENTRY_POINTS[entry], GENERATORS[generator], SCAN_SIZES)
