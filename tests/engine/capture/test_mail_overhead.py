"""The ``smtplib`` ``sendmail`` wrapper's overhead budget (W7 lane E M-E1), run last with the other budgets."""

from __future__ import annotations

import gc
import time
from typing import Any

import pytest
from tests.overhead import check_budget, paired

from fastapi import FastAPI
from mailsink import OPTIONS, harness
from sharpit import install

ROUNDS = 200
MESSAGE = "Subject: hi\n\nbody\n"


def test_suspended_mail_wrapper_overhead_budget(monkeypatch: pytest.MonkeyPatch):
    """With the mail hook suspended, the production ``sendmail`` wrapper (``_sync_sendmail`` around a no-op transport)
    costs at most 10 µs over the bare transport, even with apps installed earlier, never shut down and dropped
    (finding W7-E r2 #6: the budget timed ``_dispatch``, and leaked recorders made it 1392 µs)."""
    from sharpit.engine.capture import mail

    # Apps another test file served and never shut down are still installed (the root logger keeps their handler),
    # and every installed app records mail sent outside a request: theirs is not this wrapper's cost, so they are
    # paused for the measurement. Apps dropped without shutting down are collected, and must cost nothing.
    for installed in [o for o in gc.get_objects() if isinstance(o, mail.MailRecorder)]:
        monkeypatch.setattr(installed, "paused", True)
    for _ in range(15):
        install(FastAPI(), **OPTIONS)  # never shut down, never uninstalled, dropped at once
    gc.collect()

    def transport(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {}

    wrapper = mail._sync_sendmail(transport)  # pyright: ignore[reportPrivateUsage]
    smtp = object()
    with harness() as h:
        hook = h.hook("mail")
        assert hook is not None
        hook.suspend()

        def off_round() -> float:
            started = time.perf_counter_ns()
            for _ in range(ROUNDS):
                transport(smtp, "a@example.test", ["b@example.test"], MESSAGE)
            return (time.perf_counter_ns() - started) / ROUNDS

        def on_round() -> float:
            started = time.perf_counter_ns()
            for _ in range(ROUNDS):
                wrapper(smtp, "a@example.test", ["b@example.test"], MESSAGE)
            return (time.perf_counter_ns() - started) / ROUNDS

        result = paired(off_round, on_round, 20)
        check_budget("smtplib sendmail wrapper, suspended", result, 10_000, "µs", 1000)
