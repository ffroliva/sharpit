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
journal._status = real_status  # the finalizer fires once: this read is ours
assert [r["template"] for r in journal.records("log")] == ["logged by the other thread"]  # stored: only U's
assert journal.status()["dropped"] == {{"reentrant": 1}}  # the finalizer's record: refused and counted, never stored
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
    the handler's own lock while it waits for the journal's, or T (waiting on that lock) and U hang forever. Both
    finish, and the finalizer's record is refused and counted ``reentrant`` (#178), never stored."""
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


def test_fail_reads_the_failed_flag_only_with_its_lock_held(monkeypatch: pytest.MonkeyPatch) -> None:
    """The handler lock used to serialise the ``_failed`` check-then-set; ``_fail_lock`` must now cover every read."""
    warnings: list[logging.LogRecord] = []

    class Sink(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            warnings.append(record)

    reads: list[bool] = []

    class Watched(SharpitLogHandler):
        _flag = False

        @property
        def _failed(self) -> bool:  # pyright: ignore[reportIncompatibleVariableOverride]
            reads.append(self._fail_lock.locked())
            return self._flag

        @_failed.setter
        def _failed(self, value: bool) -> None:
            self._flag = value

    monkeypatch.setattr(logging, "lastResort", Sink())
    handler = Watched(Masker(Exposure.MASKED, True), None, lambda: None)
    threads = [threading.Thread(target=handler._fail, args=(RuntimeError("x"),)) for _ in range(4)]  # pyright: ignore[reportPrivateUsage]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert reads == [True] * 4
    assert len(warnings) == 1


class _Seen(Exception):
    """An exception whose mark lookup reports whether ``_MARK_LOCK`` is held while the host's ``__getattr__`` runs."""

    def __init__(self) -> None:
        super().__init__("seen")
        self.lookups: list[bool] = []

    def __getattr__(self, name: str) -> object:
        if name.startswith("__sharpit_seen"):
            self.__dict__.setdefault("lookups", []).append(exceptions_module._MARK_LOCK.locked())  # pyright: ignore[reportPrivateUsage]
        raise AttributeError(name)


def test_mark_seen_runs_no_host_lookup_under_the_lock_for_an_exception_already_marked() -> None:
    """The common repeat (the same exception logged again in the same request) needs no lock and no host call under it."""
    error = _Seen()
    assert exceptions_module.mark_seen(error, "req-1", "_lookup") is True
    error.lookups.clear()
    exceptions_module._FALLBACK[(id(error), "_lookup")] = "req-1"  # pyright: ignore[reportPrivateUsage]
    assert exceptions_module.mark_seen(error, "req-1", "_lookup") is False
    assert error.lookups == [False]


def test_mark_seen_counts_one_exception_logged_on_two_threads_once() -> None:
    """Both threads see no mark: the lock must make the second one re-read and see the first's."""
    error = ValueError("one exception")
    firsts: list[bool] = []
    start = threading.Barrier(2, timeout=5)

    def mark() -> None:
        start.wait()
        firsts.append(exceptions_module.mark_seen(error, None, "_race"))

    threads = [threading.Thread(target=mark) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert firsts.count(True) == 1


class _ProbeLock:
    """The buffer's lock, recording whether this thread's flag is up when the lock is taken and when it is left."""

    def __init__(self, held: threading.local) -> None:
        self.held, self.real = held, threading.Lock()
        self.entered: list[bool] = []
        self.leaving: list[bool] = []

    def __enter__(self) -> bool:
        self.entered.append(getattr(self.held, "on", False))
        return self.real.__enter__()

    def __exit__(self, *exc: object) -> None:
        self.leaving.append(getattr(self.held, "on", False))
        self.real.__exit__(*exc)


def test_the_buffer_flag_is_up_before_the_lock_is_taken_and_down_after_it_is_released() -> None:
    """A finalizer in either gap must be dropped, not wait on the lock this thread holds: the same order as
    ``exceptions._guarded``."""
    from sharpit.engine.capture.logtail import LogTailBuffer

    buffer = LogTailBuffer(10, 10_000)
    probe = _ProbeLock(buffer._held)  # pyright: ignore[reportPrivateUsage]
    buffer._lock = probe  # pyright: ignore[reportPrivateUsage,reportAttributeAccessIssue]
    buffer.append({"message": "m", "thread": "t"})
    buffer.clear()
    assert probe.entered == [True, True]
    assert probe.leaving == [True, True]
