"""``LogTailBuffer`` and ``SharpitLogHandler`` (F5, spec §7.5, §6.1 "Root handler and the console").

Ported from BootUI ``LogTailBufferTests`` (cited per test): ``evictsOldestPastLineCap``,
``evictsOldestPastByteCapButKeepsAtLeastOne``, ``reentrantAppendFromSubscriberIsDroppedNotRecursive``.
``subscribeWithReplayReturnsBacklogAndDeliversLiveWithoutGap`` is in ``test_streams.py`` (the line stream reads the
buffer by sequence number).
"""

from __future__ import annotations

import contextlib
import gc
import logging
import threading
from collections import deque
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from sharpit.engine.capture import logtail
from sharpit.engine.capture.logtail import LINE_KEYS, MAX_MESSAGE, LogTailBuffer, SharpitLogHandler
from sharpit.engine.masking import MASK, Exposure, Masker
from sharpit.engine.sqltext import Dialect

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjb3JwdXMifQ.c2lnbmF0dXJlLWJ5dGVz"
MASKED = Masker(Exposure.MASKED, True)


def _line(message: str) -> dict[str, Any]:
    return {"timestamp": 0, "level": "INFO", "logger": "test", "message": message, "thread": "main"}


def _messages(buffer: LogTailBuffer) -> list[str | None]:
    return [line["message"] for line in buffer.recent()]


def test_evicts_oldest_past_line_cap():
    # ported: evictsOldestPastLineCap
    buffer = LogTailBuffer(3, 1 << 20)
    for i in range(5):
        buffer.append(_line(f"m{i}"))
    assert _messages(buffer) == ["m2", "m3", "m4"]


def test_evicts_oldest_past_byte_cap_but_keeps_at_least_one():
    # ported: evictsOldestPastByteCapButKeepsAtLeastOne (message + thread bytes, UTF-8)
    buffer = LogTailBuffer(500, 10)
    for message in ("a", "b", "c"):  # 1 + 4 bytes each
        buffer.append(_line(message))
    assert _messages(buffer) == ["b", "c"]
    buffer.append(_line("x" * 100))
    assert len(buffer.recent()) == 1


def test_sequence_numbers_and_after():
    buffer = LogTailBuffer(2, 1 << 20)
    assert [buffer.append(_line(m)) for m in ("a", "b", "c")] == [1, 2, 3]
    assert [s for s, _ in buffer.after(None)] == [2, 3]
    assert [s for s, _ in buffer.after(2)] == [3]
    assert buffer.after(3) == []
    assert len(buffer.boot_nonce) >= 8
    assert LogTailBuffer(1, 1).boot_nonce != buffer.boot_nonce


@pytest.fixture
def isolated() -> Iterator[logging.Logger]:
    """A fresh logger that does not propagate (pytest still adds its capture handlers to it per test phase)."""
    logger = logging.getLogger("unconfigured_host.app")
    logger.propagate = False
    try:
        yield logger
    finally:
        logger.handlers[:] = []
        logger.propagate = True


@contextlib.contextmanager
def bare(*loggers: logging.Logger) -> Iterator[logging.Logger]:
    """Root and ``loggers`` without pytest's handlers; pytest adds them per test phase, so use it in the test body."""
    root = logging.getLogger()
    saved = [(lg, list(lg.handlers)) for lg in (root, *loggers)]
    for lg, _ in saved:
        lg.handlers[:] = []
    try:
        yield root
    finally:
        for lg, handlers in saved:
            lg.handlers[:] = handlers


def _handler(masker: Masker = MASKED, max_lines: int = 500) -> tuple[SharpitLogHandler, LogTailBuffer]:
    buffer = LogTailBuffer(max_lines, 1 << 20)
    return SharpitLogHandler(masker, buffer, application=lambda: None), buffer


def test_handler_level_notset_changes_no_level(isolated: logging.Logger):
    handler, buffer = _handler()
    assert handler.level == logging.NOTSET
    root = logging.getLogger()
    isolated.addHandler(handler)
    levels = (root.level, isolated.level, isolated.getEffectiveLevel())
    assert levels[2] == logging.WARNING
    isolated.info("not enabled")  # the app's levels decide, sharpit lowers nothing
    isolated.warning("seen")
    assert (root.level, isolated.level, isolated.getEffectiveLevel()) == levels
    assert _messages(buffer) == ["seen"]


def test_line_shape(isolated: logging.Logger):
    handler, buffer = _handler()
    isolated.addHandler(handler)
    isolated.warning("hello %s", "world")
    (line,) = buffer.recent()
    assert tuple(line) == LINE_KEYS == ("timestamp", "level", "logger", "message", "thread", "messageOmitted")
    assert (line["level"], line["logger"], line["message"]) == ("WARNING", isolated.name, "hello world")
    assert isinstance(line["timestamp"], int)
    assert line["timestamp"] > 1_600_000_000_000
    assert line["thread"] == "MainThread"


def test_sharpit_logger_ignored(capfd: pytest.CaptureFixture[str]):
    handler, buffer = _handler()
    with bare() as root:
        root.addHandler(handler)
        logging.getLogger("sharpit").warning("own record")
        logging.getLogger("sharpit.capture").warning("own child record")
        logging.getLogger("sharpitlike").warning("someone else")
    assert _messages(buffer) == ["someone else"]
    assert capfd.readouterr().err == "own record\nown child record\nsomeone else\n"  # still printed, as before


def test_message_masked_and_cut(isolated: logging.Logger):
    handler, buffer = _handler()
    isolated.addHandler(handler)
    isolated.warning("login password=%s token %s", "hunter2", JWT)
    isolated.warning("x" * 10_000 + " password=hunter2")
    first, second = _messages(buffer)
    assert first == f"login password={MASK}"
    assert second is not None
    assert len(second) == MAX_MESSAGE == 4000
    assert "hunter2" not in second


def test_mask_work_is_bounded_on_huge_message(isolated: logging.Logger):
    # review r0: a 10 MB message ran every mask regex over all 10 MB on the host's logging thread
    seen: list[int] = []

    class Recording(Masker):
        def mask_text(self, text: str | None) -> str | None:
            seen.append(len(text or ""))
            return super().mask_text(text)

    handler, buffer = _handler(Recording(Exposure.MASKED, True))
    isolated.addHandler(handler)
    isolated.warning("password=hunter2 " + "x" * 1_000_000)
    assert seen
    assert max(seen) <= 4 * MAX_MESSAGE
    (message,) = _messages(buffer)
    assert message == f"password={MASK}"


def test_resume_point_rejects_non_ascii_digits():
    # review r0: "²".isdigit() is True but int("²") raises, so the stream answered 500
    buffer = LogTailBuffer(10, 1 << 20)
    assert buffer.resume_point(f"{buffer.boot_nonce}-²") is None
    assert buffer.resume_point(f"{buffer.boot_nonce}-7") == 7


def test_bad_format_falls_back_to_msg(isolated: logging.Logger):
    handler, buffer = _handler()
    with bare(isolated):  # pytest's own capture handler would raise on the bad record
        isolated.addHandler(handler)
        isolated.addHandler(logging.NullHandler())  # the app's handler: no lastResort "Logging error" print
        isolated.warning("needs %s %s", "one")  # getMessage() raises
    assert _messages(buffer) == ["needs %s %s"]


def test_metadata_only_log_message_null(isolated: logging.Logger):
    handler, buffer = _handler(Masker(Exposure.METADATA_ONLY, True))
    isolated.addHandler(handler)
    isolated.warning("password=hunter2")
    (line,) = buffer.recent()
    assert line["message"] is None
    assert line["logger"] == isolated.name


@pytest.mark.parametrize("capture", [False, True])
def test_sqlalchemy_param_lines_dropped(isolated: logging.Logger, capture: bool):
    handler, buffer = _handler(Masker(Exposure.MASKED, True, capture_parameters=capture))
    engine_log = logging.getLogger("sqlalchemy.engine.Engine")
    engine_log.addHandler(handler)
    saved = engine_log.level
    engine_log.setLevel(logging.INFO)
    try:
        engine_log.info("SELECT * FROM users WHERE name = ?")
        engine_log.info("[%s] %r", "generated in 0.0001s", ("bob",))  # SQLAlchemy 2.x echo parameter line
        engine_log.info("[raw sql] %r", ("bob",))
        engine_log.info("COMMIT")
    finally:
        engine_log.setLevel(saved)
        engine_log.removeHandler(handler)
    expected = ["SELECT * FROM users WHERE name = ?", "COMMIT"]
    if capture:
        expected[1:1] = ["[generated in 0.0001s] ('bob',)", "[raw sql] ('bob',)"]
    assert _messages(buffer) == expected


def test_unconfigured_app_still_prints_warning(isolated: logging.Logger, capfd: pytest.CaptureFixture[str]):
    handler, buffer = _handler()
    other, _ = _handler()  # a second install's handler: still printed once
    isolated.propagate = True
    with bare(isolated) as root:
        root.addHandler(handler)
        root.addHandler(other)
        isolated.warning("disk almost full")
        isolated.info("quiet")
        assert capfd.readouterr().err == "disk almost full\n"  # logging.lastResort, as without sharpit
        assert _messages(buffer) == ["disk almost full"]

        configured = logging.StreamHandler()
        isolated.addHandler(configured)  # a handler of the app's own: lastResort is no longer used
        isolated.warning("handled")
        isolated.removeHandler(configured)
    assert capfd.readouterr().err == "handled\n"


def test_reentrant_record_dropped_not_recursive(isolated: logging.Logger):
    # ported: reentrantAppendFromSubscriberIsDroppedNotRecursive (a hook that logs while the handler runs)
    handler, buffer = _handler()
    isolated.addHandler(handler)
    handler.on_exc_info = lambda _record: isolated.error("from inside the handler")
    try:
        raise ValueError("boom")
    except ValueError:
        isolated.exception("failed")
    assert _messages(buffer) == ["failed"]


def test_on_exc_info_sees_exception_records(isolated: logging.Logger):
    handler, _ = _handler()
    seen: list[logging.LogRecord] = []
    handler.on_exc_info = seen.append
    isolated.addHandler(handler)
    isolated.warning("plain")
    try:
        raise ValueError("boom")
    except ValueError:
        isolated.exception("failed")
    assert [r.getMessage() for r in seen] == ["failed"]


def test_log_handler_failure_silent(
    isolated: logging.Logger, capfd: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    handler, buffer = _handler()
    isolated.addHandler(handler)
    isolated.addHandler(logging.NullHandler())  # the app is configured: only sharpit's own warning reaches stderr

    def broken(_line: dict[str, Any]) -> int:
        raise RuntimeError("store failed")

    monkeypatch.setattr(buffer, "append", broken)
    isolated.warning("one")
    isolated.warning("two")
    err = capfd.readouterr().err
    assert "Traceback" not in err
    assert "store failed" not in err
    assert err.count("sharpit") == 1, err
    assert "RuntimeError" in err, err


def test_log_tail_line_sets_message_omitted_in_metadata_only_mode():
    # ported: LogTailStoreTests.setsMessageOmittedWhenMetadataOnly (BootUI 2.2.0 LogLineDto.messageOmitted)
    record = logging.LogRecord("app", logging.INFO, __file__, 1, "token=%s", ("abc",), None)
    hidden = _handler(Masker(Exposure.METADATA_ONLY, True))[0].line(record)
    assert hidden is not None
    assert hidden["message"] is None
    assert hidden.get("messageOmitted") is True, "a withheld message says so"
    for exposure in (Exposure.MASKED, Exposure.FULL):
        shown = _handler(Masker(exposure, True))[0].line(record)
        assert shown is not None
        assert shown.get("messageOmitted") is False, exposure


def test_the_line_keeps_a_falsy_application_family(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(Dialect, "__bool__", lambda _self: False, raising=False)
    seen: list[Dialect] = []

    def spy(_masker: Masker, text: str, dialect: Dialect) -> str:
        seen.append(dialect)
        return text

    monkeypatch.setattr(logtail, "error_text", spy)
    handler = SharpitLogHandler(MASKED, None, lambda: Dialect.SQLITE)
    handler.line(logging.makeLogRecord({"name": "host", "msg": "line"}))
    assert seen == [Dialect.SQLITE]


@pytest.mark.parametrize("read", [LogTailBuffer.recent, lambda buffer: buffer.after(None)], ids=["recent", "after"])
def test_a_finalizer_that_logs_during_a_read_does_not_deadlock(read: Callable[[LogTailBuffer], list[Any]]):
    """A collection on the reader's thread runs a finalizer, which logs, which appends: a held lock hangs that thread.

    The finalizer appends directly: a hung ``emit`` would keep the handler's lock and hang ``logging.shutdown`` too.
    """
    buffer = LogTailBuffer(5, 1 << 20)
    buffer.append(_line("first"))

    class Finalized:
        def __del__(self) -> None:
            buffer.append(_line("from a finalizer"))

    class Collected(deque[Any]):
        def __iter__(self) -> Iterator[Any]:
            garbage = Finalized()
            garbage.cycle = garbage  # pyright: ignore[reportAttributeAccessIssue]
            del garbage
            gc.collect()
            return super().__iter__()

    buffer._lines = Collected(buffer._lines)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    finished = threading.Event()

    def run() -> None:
        read(buffer)
        finished.set()

    threading.Thread(target=run, daemon=True).start()
    assert finished.wait(5)
    assert _messages(buffer)[:2] == ["first", "from a finalizer"]  # this read collects again and may add a third


class _CustomStrError(Exception):
    def __str__(self) -> str:
        return "custom __str__ text"


class _AppStatementError(Exception):
    def __init__(self, statement: str) -> None:
        super().__init__(statement)
        self.statement = statement


class _RaisingStrError(Exception):
    def __str__(self) -> str:
        raise RuntimeError("unprintable")


@pytest.mark.parametrize(
    ("fmt", "args", "expected"),
    [
        ("retrying after %s", (ValueError("timeout"),), "retrying after timeout"),
        (
            "%s",
            (OSError(2, "No such file or directory", "/tmp/x.db"),),
            "[Errno 2] No such file or directory: '/tmp/x.db'",
        ),
        ("%s", (_CustomStrError("raw args"),), "custom __str__ text"),
        ("%s", (_AppStatementError('note: "keep"'),), 'note: "keep"'),
        (
            "retrying %s after %s",
            (
                ValueError("timeout"),
                type("OperationalError", (Exception,), {"__module__": "sqlite3"})("near 'secret_token': syntax error"),
            ),
            "retrying timeout after OperationalError",
        ),
        (
            "retrying after %s password=hunter2",
            (_RaisingStrError("raw args"),),
            f"retrying after %s password={MASK}",
        ),
    ],
    ids=[
        "retrying_prefix",
        "oserror_filename",
        "custom_str",
        "unclassified_statement",
        "classified_driver_in_args",
        "raising_str",
    ],
)
def test_log_record_exception_args_follow_chain_classification(
    isolated: logging.Logger, fmt: str, args: tuple[object, ...], expected: str
) -> None:
    # derived: D5 logtail exception args classification (a7a6ff2f base parity vs read_chain driver objects)
    handler, buffer = _handler()
    with bare(isolated):
        isolated.addHandler(handler)
        isolated.addHandler(logging.NullHandler())
        isolated.error(fmt, *args)
    (message,) = _messages(buffer)
    assert "secret_token" not in (message or "")
    assert message == expected


# derived: Task 27 review 4 (subclass __class__ descriptor on a log arg never runs and record is still logged)
def test_logtail_arg_with_raising_class_property_is_still_logged() -> None:
    ran: list[str] = []

    class HostileArgError(Exception):
        @property
        def __class__(self) -> type:  # type: ignore[override]
            ran.append("__class__")
            raise RuntimeError("__class__ descriptor ran")

    handler, buffer = _handler()
    record = logging.makeLogRecord(
        {
            "name": "host",
            "levelno": logging.ERROR,
            "levelname": "ERROR",
            "msg": "hello %s",
            "args": (HostileArgError("bad"),),
        }
    )
    handler.emit(record)
    assert ran == []
    assert _messages(buffer) == ["hello bad"]


# derived: Task 27 review 8 (classified psycopg arg in log record substitutes safe rendering into record.msg)
def test_logtail_classified_psycopg_arg_keeps_format_text_without_driver_text(isolated: logging.Logger) -> None:
    psycopg_errors = pytest.importorskip("psycopg.errors")
    handler, buffer = _handler()
    with bare(isolated):
        isolated.addHandler(handler)
        isolated.addHandler(logging.NullHandler())
        isolated.error(
            "retrying after %s",
            psycopg_errors.InvalidTextRepresentation('invalid input syntax for type integer: "hunter2secret"'),
        )
    assert _messages(buffer) == ["retrying after (psycopg.errors.InvalidTextRepresentation) 22P02"]
