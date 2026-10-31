"""``LogTailBuffer`` and ``SharpitLogHandler`` (F5, spec §7.5, §6.1 "Root handler and the console").

Ported from BootUI ``LogTailBufferTests`` (cited per test): ``evictsOldestPastLineCap``,
``evictsOldestPastByteCapButKeepsAtLeastOne``, ``reentrantAppendFromSubscriberIsDroppedNotRecursive``.
``subscribeWithReplayReturnsBacklogAndDeliversLiveWithoutGap`` is in ``test_streams.py`` (the line stream reads the
buffer by sequence number).
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator
from typing import Any

import pytest

from sharpit.engine.capture.logtail import LINE_KEYS, MAX_MESSAGE, LogTailBuffer, SharpitLogHandler
from sharpit.engine.masking import MASK, Exposure, Masker

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
    assert len(buffer.boot_nonce) >= 8 and LogTailBuffer(1, 1).boot_nonce != buffer.boot_nonce


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
    return SharpitLogHandler(masker, buffer), buffer


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
    assert tuple(line) == LINE_KEYS == ("timestamp", "level", "logger", "message", "thread")
    assert (line["level"], line["logger"], line["message"]) == ("WARNING", isolated.name, "hello world")
    assert isinstance(line["timestamp"], int) and line["timestamp"] > 1_600_000_000_000  # epoch millis
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
    assert first == f"login password={MASK} token {MASK}"
    assert second is not None and len(second) == MAX_MESSAGE == 4000 and "hunter2" not in second


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
    assert line["message"] is None and line["logger"] == isolated.name


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
    assert "Traceback" not in err and "store failed" not in err
    assert err.count("sharpit") == 1 and "RuntimeError" in err, err
