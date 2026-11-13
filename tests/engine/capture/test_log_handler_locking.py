"""The sharpit log handlers hold no handler lock across ``emit`` (``logging.Handler.handle`` would): a thread that
holds the journal lock or the test sink's lock and logs from a GC finalizer must not wait on a lock another thread holds
across a wait for the first one.

A deadlock scenario runs in a child process under a timeout: a regression is then a clean red, not threads that outlive
the test and hang the interpreter at exit (``logging.shutdown`` takes the handler lock)."""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from sharpit.engine.capture import exceptions as exceptions_module
from sharpit.engine.capture.logtail import SharpitLogHandler
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.testsession.sink import TestSessionSink
from sharpit.pytest_plugin import _ExceptionHandler  # pyright: ignore[reportPrivateUsage]

DONE = "both threads finished"
CHILD_TIMEOUT = 20

_LOG_HANDLER_CHILD = f"""
import logging, threading
from fastapi import FastAPI
from sharpit import install

handle = install(FastAPI(), enabled="ON", show_banner=False, config_scan=False, runtime_journal_sources=("log",))
journal = handle.context.capture.journal
handler = handle.context.capture.wiring.log_handler
real_status, real_accepts = journal._status, journal.accepts
reader_in_lock, u_in_emit = threading.Event(), threading.Event()


def emit(msg):
    record = logging.LogRecord("com.example.orders.OrderService", logging.WARNING, "child.py", 1, msg, None, None)
    handler.handle(record)


def status_with_finalizer():
    reader_in_lock.set()  # T holds the journal lock from here
    assert u_in_emit.wait(10)
    emit("finalizer on the journal-holding thread")  # a GC finalizer logging, as asyncio and SQLAlchemy do
    return real_status()


def accepts(source):
    if threading.current_thread().name == "U":
        u_in_emit.set()  # U is inside emit, past any handler lock, about to offer
    return real_accepts(source)


journal._status, journal.accepts = status_with_finalizer, accepts


def u_logs():
    assert reader_in_lock.wait(10)
    emit("logged by the other thread")


threads = [threading.Thread(target=journal.status, name="T"), threading.Thread(target=u_logs, name="U")]
for t in threads:
    t.start()
for t in threads:
    t.join()
assert sorted(r["template"] for r in journal.records("log")) == [
    "finalizer on the journal-holding thread",
    "logged by the other thread",
]
print({DONE!r})
"""

_EXCEPTION_HANDLER_CHILD = f"""
import logging, threading
from sharpit.engine.testsession.sink import TestSessionSink
from sharpit.pytest_plugin import _ExceptionHandler

sink = TestSessionSink("gw0")
handler = _ExceptionHandler(sink)
t_in_lock, u_in_emit = threading.Event(), threading.Event()
real_on_exception = sink.on_exception


def on_exception(exc, source, test):
    if threading.current_thread().name == "U":
        u_in_emit.set()  # U is inside emit, past any handler lock, about to take the sink lock
    return real_on_exception(exc, source, test)


sink.on_exception = on_exception


def emit(error):
    info = (type(error), error, None)
    handler.handle(logging.LogRecord("app", logging.ERROR, "child.py", 1, "boom", None, info))


def t_holds_sink_lock():
    with sink._lock:
        t_in_lock.set()
        assert u_in_emit.wait(10)
        emit(ValueError("finalizer on the sink-holding thread"))  # a GC finalizer logging


def u_logs():
    assert t_in_lock.wait(10)
    emit(KeyError("logged by the other thread"))


threads = [threading.Thread(target=t_holds_sink_lock, name="T"), threading.Thread(target=u_logs, name="U")]
for t in threads:
    t.start()
for t in threads:
    t.join()
print({DONE!r})
"""

_CLEAR_CHILD = f"""
import logging
from collections import deque
from sharpit.engine.capture.logtail import LogTailBuffer, SharpitLogHandler
from sharpit.engine.masking import Exposure, Masker

buffer = LogTailBuffer(10, 10_000)
handler = SharpitLogHandler(Masker(Exposure.MASKED, True), buffer, lambda: None)


class FinalizerDeque(deque):
    def clear(self):
        # a GC finalizer logging on the thread that holds the buffer lock, as asyncio and SQLAlchemy do
        handler.handle(logging.LogRecord("app", logging.INFO, "child.py", 1, "from a finalizer", None, None))
        super().clear()


buffer.append({{"message": "kept until clear", "thread": "t"}})
buffer._lines = FinalizerDeque(buffer._lines)
buffer.clear()
print({DONE!r})
"""


def _run_child(script: str, tmp_path: Path) -> str:
    """Run in ``tmp_path`` with its own state dir: the child's install must write nothing under the repo root."""
    try:
        done = subprocess.run(  # noqa: S603 - our own interpreter and a literal script
            [sys.executable, "-c", textwrap.dedent(script)],
            capture_output=True,
            text=True,
            timeout=CHILD_TIMEOUT,
            check=False,
            cwd=tmp_path,
            env={**os.environ, "SHARPIT_STATE_DIR": str(tmp_path / "state")},
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"deadlock: the child did not finish within {CHILD_TIMEOUT}s")
    assert done.returncode == 0, done.stderr
    return done.stdout


def test_log_handler_never_holds_its_lock_across_the_journal_offer(tmp_path: Path) -> None:
    """Thread T holds the journal lock (a read) and a GC finalizer on T logs while thread U logs: U must not hold
    the handler's own lock while it waits for the journal's, or T (waiting on that lock) and U hang forever."""
    assert DONE in _run_child(_LOG_HANDLER_CHILD, tmp_path)


def test_exception_handler_never_holds_its_lock_across_the_sink_lock(tmp_path: Path) -> None:
    """The pytest plugin's handler had the same cycle: handler lock then sink lock, against sink lock then a finalizer's
    log waiting on the handler lock."""
    assert DONE in _run_child(_EXCEPTION_HANDLER_CHILD, tmp_path)


def test_clear_does_not_deadlock_on_a_finalizer_that_logs(tmp_path: Path) -> None:
    """``clear`` holds the buffer's non-reentrant lock; a finalizer on that thread logs into ``append``."""
    assert DONE in _run_child(_CLEAR_CHILD, tmp_path)


def _record() -> logging.LogRecord:
    return logging.LogRecord("app", logging.WARNING, __file__, 1, "m", None, None)


@pytest.mark.parametrize("kind", ["log", "exception"])
def test_handle_returns_what_the_filters_return(kind: str) -> None:
    """stdlib ``Handler.handle`` (3.12+) returns the record when the filters pass it, a falsy value when they refuse."""
    handler: logging.Handler = (
        SharpitLogHandler(Masker(Exposure.MASKED, True), None, lambda: None)
        if kind == "log"
        else _ExceptionHandler(TestSessionSink("gw0"))
    )
    record = _record()
    assert handler.handle(record) is record
    handler.addFilter(lambda _record: False)
    assert not handler.handle(record)


def test_fail_warns_once_when_threads_fail_at_the_same_time(monkeypatch: pytest.MonkeyPatch) -> None:
    """The handler lock used to serialise the ``_failed`` check-then-set: with none, two threads could both warn."""
    meet = threading.Barrier(4)
    warnings: list[logging.LogRecord] = []

    class Sink(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            warnings.append(record)

    class Racy(SharpitLogHandler):
        """Every thread reads ``_failed`` while it is still unset and waits there for the others."""

        _flag = False

        @property
        def _failed(self) -> bool:  # pyright: ignore[reportIncompatibleVariableOverride]
            seen = self._flag
            if not seen:
                with contextlib.suppress(threading.BrokenBarrierError):
                    meet.wait(0.3)
            return seen

        @_failed.setter
        def _failed(self, value: bool) -> None:
            self._flag = value

    monkeypatch.setattr(logging, "lastResort", Sink())
    handler = Racy(Masker(Exposure.MASKED, True), None, lambda: None)
    threads = [threading.Thread(target=handler._fail, args=(RuntimeError("x"),)) for _ in range(4)]  # pyright: ignore[reportPrivateUsage]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(warnings) == 1


def test_mark_seen_counts_one_exception_logged_on_two_threads_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both threads read the mark before either writes it: the store's lock must make the second one see the first's."""
    meet = threading.Barrier(2)
    real = exceptions_module._mark  # pyright: ignore[reportPrivateUsage]

    def mark_then_meet(exc: BaseException, slot: str) -> str | None:
        prior = real(exc, slot)
        with contextlib.suppress(threading.BrokenBarrierError):
            meet.wait(0.3)
        return prior

    monkeypatch.setattr(exceptions_module, "_mark", mark_then_meet)
    error = ValueError("one exception")
    firsts: list[bool] = []
    threads = [
        threading.Thread(target=lambda: firsts.append(exceptions_module.mark_seen(error, None, "_race")))
        for _ in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert firsts.count(True) == 1
