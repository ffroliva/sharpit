"""Class gate: masking holds the GIL, so a superlinear pass on a client-sized value freezes the host.

Each doubling must cost less than 3 times the last, and 32 KB under a second. This measures CPU time, which a busy
machine does not inflate: the minimum of a few repeats, re-measured when a step fails, a floor under millisecond noise.
A new heuristic only has to survive these generators to ship; add the input that broke it here.
"""

from __future__ import annotations

import gc
import time
from collections.abc import Callable

import pytest

from sharpit.engine import masking
from sharpit.engine.capture import sqlscan
from sharpit.engine.capture.sqlscan import shown
from sharpit.engine.capture.sqltrace import mask_error
from sharpit.engine.masking import Exposure, Masker

MASKER = Masker(Exposure.MASKED, True)
SIZES = (4_000, 8_000, 16_000, 32_000)
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
    "escaped-quote-run": lambda size: "password=[" + ESCAPED_QUOTE * (size // 2) + "]",
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
}


def _pair_substitution(text: str) -> str:
    masked = masking._mask_pairs(masking._TEXT_QUOTED_PAIR, masking._QUOTED_PAIR_MASKED, text)  # noqa: SLF001
    return masking._mask_pairs(masking._TEXT_PAIR, masking._PAIR_MASKED, masked)  # noqa: SLF001


ENTRY_POINTS: dict[str, Callable[[str], object]] = {
    "mask_text": MASKER.mask_text,
    "mask_error": lambda text: mask_error(MASKER, text),
    "pair_substitution": _pair_substitution,
    "shown_overlapping_spans": lambda text: shown(text, [(start, len(text)) for start in range(len(text))]),
}


def _seconds(entry: Callable[[str], object], text: str) -> float:
    best = float("inf")
    for repeat in range(REPEATS):
        runs = 0
        started = time.process_time()
        while (spent := time.process_time() - started) < MIN_SAMPLE_SECONDS:  # the clock ticks every 15.6 ms on Windows
            runs += 1
            entry(f"{text} {repeat} {runs}")  # unique: past the normaliser's cache
        best = min(best, spent / runs)
    return best


def _step(entry: Callable[[str], object], make: Callable[[int], str], size: int) -> float:
    """How many times the half size ``size`` costs: a busy machine can fail a step, a quadratic pass fails every one."""
    step = float("inf")
    for _ in range(ATTEMPTS):
        half = _seconds(entry, make(size // 2))
        full = _seconds(entry, make(size))
        step = min(step, (full + FLOOR_SECONDS) / (half + FLOOR_SECONDS))
        if step < MAX_STEP:
            break
    return step


def _flags_of_overlapping_spans(text: str) -> bytearray:
    spans = [(start, len(text)) for start in range(len(text))]
    return sqlscan._hidden_flags(spans, len(text))  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


def test_overlapping_hidden_spans_are_written_once() -> None:
    """Direct, and far past ``SIZES``: writing a span again is a ``memset``, too cheap to see under the scan's cost."""
    size = 200_000
    step = _step(_flags_of_overlapping_spans, GENERATORS["closers"], size)
    assert step < MAX_STEP, f"{size} chars cost {step:.1f}x the half size"


@pytest.mark.parametrize("entry", ENTRY_POINTS)
@pytest.mark.parametrize("generator", GENERATORS)
def test_masking_scales_linearly(entry: str, generator: str) -> None:
    run, make = ENTRY_POINTS[entry], GENERATORS[generator]
    gc_was_on = gc.isenabled()
    gc.disable()
    try:
        for size in SIZES[1:]:  # smallest first: a quadratic pass fails before it runs into the test timeout
            step = _step(run, make, size)
            assert step < MAX_STEP, f"{size} chars cost {step:.1f}x the half size"
        largest = _seconds(run, make(SIZES[-1]))
    finally:
        if gc_was_on:
            gc.enable()
    assert largest < MAX_SECONDS
