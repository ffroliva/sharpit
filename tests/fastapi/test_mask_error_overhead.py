"""``mask_error`` overhead budget on a log line: the path with no SQL marker is the path of ``mask_text``.

Every log record and exception message comes through here. "off" is a no-op called the same way, so the overhead is
``mask_error`` itself.

Rounds alternate and the first side swaps every round, through tests/overhead.py; how to read a failure:
docs/development/overhead-budgets.md.
"""

from __future__ import annotations

import sys
import time
import types
from collections.abc import Callable
from functools import partial

from tests.overhead import check_budget, paired

from sharpit.engine.capture.sqltrace import mask_error
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import Dialect

BUDGET_NS = 350_000  # fa2d51e: fastest 172 us, slowest 305 us per line (20 runs, CPU at 56%); the convention is 2x
ROUNDS, PER_ROUND = 301, 20
MASKER = Masker(Exposure.MASKED, True)
LINE = (
    "2026-11-04 12:00:01,204 ERROR app.billing charge failed for user=alice order=8812 status=502 "
    "upstream=https://pay.example.test/v1/charges token=abc123 retry in 30s"
)
Mask = Callable[[Masker, str | None, Dialect], str | None]


def _noop(masker: Masker, text: str | None, dialect: Dialect) -> str | None:
    del masker, dialect
    return text


def _round(mask: Mask) -> float:
    started = time.perf_counter_ns()
    for _ in range(PER_ROUND):
        mask(MASKER, LINE, Dialect.UNSUPPORTED)
    return (time.perf_counter_ns() - started) / PER_ROUND


def _calls_while_masking() -> list[str]:
    seen: list[str] = []

    def profile(frame: types.FrameType, event: str, _arg: object) -> None:
        if event == "call":
            seen.append(frame.f_code.co_name)

    sys.setprofile(profile)
    try:
        mask_error(MASKER, LINE, Dialect.UNSUPPORTED)
    finally:
        sys.setprofile(None)
    return seen


def test_a_log_line_reaches_the_masker_once() -> None:
    """What the budget times: a line with something to mask, through one ``mask_text`` and no error rendering."""
    masked = mask_error(MASKER, LINE, Dialect.UNSUPPORTED)
    assert masked == MASKER.mask_text(LINE)
    assert masked is not None
    assert "abc123" not in masked
    calls = _calls_while_masking()
    assert calls.count("mask_text") == 1
    assert "_mask_token" in calls


def test_mask_error_overhead() -> None:
    result = paired(partial(_round, _noop), partial(_round, mask_error), ROUNDS)
    check_budget("mask_error on a log line", result, BUDGET_NS, "µs", 1000)
