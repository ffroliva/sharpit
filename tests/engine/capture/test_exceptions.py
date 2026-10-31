"""``ExceptionStore``, fingerprints, dedup marks and application frames (F2, spec §7.2).

Ported from BootUI ``ExceptionStoreTests`` (cited per test). Not ported: ``appliesIgnorePredicate`` (no adapter
noise filter in sharpit), ``flagsApplicationFramesFromConfiguredPackages`` (sharpit uses the file-path rule, tested
in ``test_is_application_frame_table``), the span-enricher tests (no OpenTelemetry), and
``deduplicatesAcrossCauseChain...`` (sharpit dedups by a per-request mark on the exception, spec §7.2).
"""

from __future__ import annotations

import asyncio
import gc
import os
import sysconfig
import threading
from collections.abc import Callable
from typing import Any

import pytest

from sharpit.engine.capture.correlation import RequestInfo
from sharpit.engine.capture.exceptions import (
    GROUP_KEYS,
    MAX_MESSAGE,
    ExceptionStore,
    fingerprint,
    mark_seen,
)
from sharpit.engine.capture.frames import is_application_frame
from sharpit.engine.masking import MASK, Exposure, Masker

MASKED = Masker(Exposure.MASKED, True)
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjb3JwdXMifQ.c2lnbmF0dXJlLWJ5dGVz"


def _store(groups: int = 100, occurrences: int = 25, frames: int = 50, masker: Masker = MASKED) -> ExceptionStore:
    return ExceptionStore(groups, occurrences, frames, masker)


def _raised(factory: Callable[[], BaseException]) -> BaseException:
    try:
        raise factory()
    except BaseException as exc:  # noqa: BLE001
        return exc


def _same_origin(count: int) -> list[BaseException]:
    return [_raised(lambda: ValueError("repeated failure")) for _ in range(count)]


def _request(rid: str = "r1") -> RequestInfo:
    return RequestInfo(rid, "ctx", "GET", "/x", "app:x", 0, None)


def _record(store: ExceptionStore, exc: BaseException, request: RequestInfo | None = None, **kw: Any) -> None:
    store.record(exc, kw.pop("source", "log"), request, kw.pop("thread", "main"), **kw)


def _groups(store: ExceptionStore) -> list[dict[str, Any]]:
    return store.report()["groups"]


def test_groups_repeated_failures():
    # ported: groupsRepeatedFailuresWithIdenticalStacks
    store = _store()
    for exc in _same_origin(3):
        _record(store, exc)
    groups = _groups(store)
    assert len(groups) == 1 and groups[0]["count"] == 3
    assert store.report()["totalExceptions"] == 3


def test_dedup_same_instance_same_request():
    # ported: deduplicatesTheSameThrowableInstance
    store = _store()
    exc = _raised(lambda: RuntimeError("boom"))
    _record(store, exc, _request(), source="request")
    _record(store, exc, _request(), source="log")
    assert store.report()["totalExceptions"] == 1 and _groups(store)[0]["lastSource"] == "request"


def test_separates_distinct_types():
    # ported: separatesDistinctExceptionTypes
    store = _store()
    _record(store, _raised(lambda: RuntimeError("a")))
    _record(store, _raised(lambda: ValueError("b")))
    assert len(_groups(store)) == 2


def test_evicts_oldest_last_seen():
    # ported: evictsTheLeastRecentlySeenGroupWhenFull (ordered by ns internally: no sleep needed)
    store = _store(groups=2)
    for factory in (lambda: RuntimeError("1"), lambda: ValueError("2"), lambda: KeyError("3")):
        _record(store, _raised(factory))
    assert sorted(g["exceptionClassName"] for g in _groups(store)) == ["KeyError", "ValueError"]


def test_bounds_occurrences_per_group():
    # ported: boundsRetainedOccurrencesPerGroup
    store = _store(occurrences=3)
    for exc in _same_origin(5):
        _record(store, exc)
    group = _groups(store)[0]
    detail = store.detail(group["id"])
    assert detail is not None
    assert group["count"] == 5 and len(detail["occurrences"]) == 3


def test_cause_chain():
    # ported: capturesCauseChainWithCommonFrameCount
    store = _store()

    def wrapped() -> BaseException:
        try:
            int("x")
        except ValueError:
            return _raised(lambda: RuntimeError("wrapped"))
        raise AssertionError  # pragma: no cover

    exc = _raised(lambda: RuntimeError("outer"))
    exc.__cause__ = _raised(lambda: ValueError("bad number"))
    _record(store, exc)
    detail = store.detail(_groups(store)[0]["id"])
    assert detail is not None
    assert [c["exceptionClassName"] for c in detail["causes"]] == ["ValueError"]
    assert tuple(detail["causes"][0]) == ("exceptionClassName", "message", "frames", "commonFrames")
    implicit = wrapped()  # __context__, not suppressed
    _record(store, implicit)
    detail = store.detail(next(g["id"] for g in _groups(store) if g["message"] == "wrapped"))
    assert detail is not None and [c["message"] for c in detail["causes"]] == [
        "invalid literal for int() with base 10: 'x'"
    ]


def test_suppressed_context_not_a_cause():
    store = _store()
    exc = _raised(lambda: RuntimeError("outer"))
    exc.__context__ = _raised(lambda: ValueError("hidden"))
    exc.__suppress_context__ = True
    _record(store, exc)
    detail = store.detail(_groups(store)[0]["id"])
    assert detail is not None and detail["causes"] == []


def test_clear_and_change_signals():
    # ported: clearsState, notifiesSubscribersOnRecordAndClear..., setStatusNotifiesSubscribers
    store = _store()
    signals: list[int] = []
    store.changes.signal = lambda: signals.append(1)  # type: ignore[method-assign]
    _record(store, _raised(lambda: RuntimeError("boom")))
    assert len(signals) == 1
    store.set_status(_groups(store)[0]["id"], "ACKNOWLEDGED")
    assert len(signals) == 2
    store.clear()
    assert len(signals) == 3
    assert _groups(store) == [] and store.report()["totalExceptions"] == 0


def test_failing_signal_never_breaks_capture():
    # ported: isolatesSubscriberFailuresFromCapture
    store = _store()

    def bad() -> None:
        raise RuntimeError("bad subscriber")

    store.changes.signal = bad  # type: ignore[method-assign]
    _record(store, _raised(lambda: RuntimeError("boom")))
    assert store.report()["totalExceptions"] == 1


def test_new_group_open_no_regressions():
    # ported: newGroupsDefaultToOpenStatusWithNoRegressions
    store = _store()
    _record(store, _raised(lambda: RuntimeError("boom")))
    assert (_groups(store)[0]["status"], _groups(store)[0]["regressionCount"]) == ("OPEN", 0)


def test_set_status_known_and_unknown():
    # ported: setStatusUpdatesAKnownGroupAndReturnsTheUpdatedSummary, setStatusReturnsNullForAnUnknownFingerprint
    store = _store()
    _record(store, _raised(lambda: RuntimeError("boom")))
    gid = _groups(store)[0]["id"]
    updated = store.set_status(gid, "acknowledged")  # BootUI parses case-insensitively
    assert updated is not None and updated["status"] == "ACKNOWLEDGED"
    assert _groups(store)[0]["status"] == "ACKNOWLEDGED"
    assert store.set_status("does-not-exist", "RESOLVED") is None


@pytest.mark.parametrize("value", [None, "", "  ", "CLOSED"])
def test_invalid_status_checked_before_the_group(value: str | None):
    # ported: ExceptionsService.parseStatus / updateStatus (a bad status is a 400 even for an unknown id)
    with pytest.raises(ValueError, match=r"^Invalid status '.*'; expected one of OPEN, ACKNOWLEDGED, RESOLVED$"):
        _store().set_status("does-not-exist", value)


def test_acknowledged_does_not_auto_transition():
    # ported: acknowledgedGroupsDoNotAutoTransitionOnNewOccurrences
    store = _store()
    first, second = _same_origin(2)
    _record(store, first)
    store.set_status(_groups(store)[0]["id"], "ACKNOWLEDGED")
    _record(store, second)
    group = _groups(store)[0]
    assert (group["status"], group["regressionCount"], group["count"]) == ("ACKNOWLEDGED", 0, 2)


def test_resolved_reopens_and_counts_regressions():
    # ported: resolvedGroupsAutoReopenAndIncrementRegressionCountOnANewOccurrence
    store = _store()
    excs = _same_origin(3)
    _record(store, excs[0])
    gid = _groups(store)[0]["id"]
    for i, exc in enumerate(excs[1:], start=1):
        store.set_status(gid, "RESOLVED")
        _record(store, exc)
        assert (_groups(store)[0]["status"], _groups(store)[0]["regressionCount"]) == ("OPEN", i)


def test_manual_status_never_changes_regression_count():
    # ported: manualSetStatusNeverChangesRegressionCount
    store = _store()
    _record(store, _raised(lambda: RuntimeError("boom")))
    gid = _groups(store)[0]["id"]
    for status in ("ACKNOWLEDGED", "RESOLVED", "OPEN"):
        store.set_status(gid, status)
    assert _groups(store)[0]["regressionCount"] == 0


# --- sharpit additions (spec §7.2) ---------------------------------------------------------------------------------


MODULE_LEVEL = RuntimeError("module-level instance")


def test_module_level_instance_counted_per_request():
    store = _store()
    for rid in ("r1", "r2"):
        _record(store, MODULE_LEVEL, _request(rid), source="request")
        _record(store, MODULE_LEVEL, _request(rid), source="log")  # same request: a duplicate
    _record(store, MODULE_LEVEL, None)  # outside a request after one marked it: the server's own log of it
    assert store.report()["totalExceptions"] == 2


def test_mark_seen_rules():
    exc = RuntimeError("x")
    assert mark_seen(exc, "r1") is True
    assert mark_seen(exc, "r1") is False
    assert mark_seen(exc, None) is False  # outside any request: already recorded
    assert mark_seen(exc, "r2") is True
    fresh = RuntimeError("y")
    assert mark_seen(fresh, None) is True
    assert mark_seen(fresh, None) is False
    assert mark_seen(fresh, "r3") is True  # a later request raising it again counts again


class SlotsError(Exception):
    """Refuses new attributes, like some C-extension exceptions."""

    def __setattr__(self, name: str, value: object) -> None:
        if name.startswith("__sharpit"):
            raise AttributeError(name)
        super().__setattr__(name, value)


def test_slots_exception_fallback_set():
    store = _store()
    exc = SlotsError("no attributes")
    _record(store, exc, _request("r1"), source="request")
    _record(store, exc, _request("r1"), source="log")
    assert store.report()["totalExceptions"] == 1
    store.forget_request("r1")  # request end evicts its fallback entries
    _record(store, exc, _request("r2"), source="request")
    assert store.report()["totalExceptions"] == 2


def test_fallback_set_bounded():
    from sharpit.engine.capture import exceptions as module

    for i in range(200):
        mark_seen(SlotsError(str(i)), f"bulk-{i}")
    assert len(module._FALLBACK) <= 64  # pyright: ignore[reportPrivateUsage]


def test_exception_group_unwrap():
    store = _store()
    single = ExceptionGroup("one", [_raised(lambda: KeyError("only"))])
    _record(store, single)
    assert _groups(store)[0]["exceptionClassName"] == "KeyError"
    many = ExceptionGroup("many", [_raised(lambda: ValueError("first")), ExceptionGroup("n", [TypeError("t")])])
    _record(store, many)
    group = next(g for g in _groups(store) if g["exceptionClassName"] == "ValueError")
    detail = store.detail(group["id"])
    assert detail is not None and [c["exceptionClassName"] for c in detail["causes"]] == ["TypeError"]


def test_causes_cycle_safe_max_five():
    store = _store()
    chain = [RuntimeError(f"e{i}") for i in range(8)]
    for outer, inner in zip(chain, chain[1:], strict=False):
        outer.__cause__ = inner
    chain[-1].__cause__ = chain[0]  # a cycle
    _record(store, chain[0])
    detail = store.detail(_groups(store)[0]["id"])
    assert detail is not None and [c["message"] for c in detail["causes"]] == ["e1", "e2", "e3", "e4", "e5"]
    loop = RuntimeError("loop")
    loop.__cause__ = loop
    _record(store, loop)
    detail = store.detail(next(g["id"] for g in _groups(store) if g["message"] == "loop"))
    assert detail is not None and detail["causes"] == []


def test_message_masked_and_cut_2000():
    store = _store()
    _record(store, _raised(lambda: RuntimeError(f"login failed password=hunter2 token {JWT}")))
    assert _groups(store)[0]["message"] == f"login failed password={MASK} token {MASK}"
    _record(store, _raised(lambda: ValueError("x" * 5000)))
    long = next(g for g in _groups(store) if g["exceptionClassName"] == "ValueError")["message"]
    assert len(long) == MAX_MESSAGE == 2000 and long.endswith("…")
    cause = _raised(lambda: RuntimeError("outer"))
    cause.__cause__ = RuntimeError("api_key=s3cr3t-value")
    _record(store, cause)
    detail = store.detail(next(g["id"] for g in _groups(store) if g["message"] == "outer"))
    assert detail is not None and detail["causes"][0]["message"] == f"api_key={MASK}"


def test_message_override_used_and_masked():
    store = _store()
    _record(store, _raised(lambda: RuntimeError()), message_override="logged password=hunter2")
    assert _groups(store)[0]["message"] == f"logged password={MASK}"


def test_metadata_only_exception_message_null():
    store = _store(masker=Masker(Exposure.METADATA_ONLY, True))
    exc = _raised(lambda: RuntimeError("secret detail"))
    exc.__cause__ = RuntimeError("cause detail")
    _record(store, exc)
    group = _groups(store)[0]
    detail = store.detail(group["id"])
    assert detail is not None
    assert group["message"] is None and detail["group"]["message"] is None and detail["causes"][0]["message"] is None


def test_no_locals_in_frames():
    store = _store()

    def leaky() -> None:
        password = "hunter2-local"  # noqa: S105
        raise RuntimeError(len(password))

    _record(store, _raised(lambda: leaky() or RuntimeError()))  # type: ignore[func-returns-value]
    detail = store.detail(_groups(store)[0]["id"])
    assert detail is not None
    assert all(tuple(f) == ("declaringClass", "methodName", "fileName", "lineNumber", "applicationFrame")
               for f in detail["frames"])  # fmt: skip
    assert "hunter2-local" not in str(detail)
    innermost = detail["frames"][0]
    assert (innermost["declaringClass"], innermost["fileName"]) == (__name__, "test_exceptions.py")
    assert innermost["methodName"] == "test_no_locals_in_frames.<locals>.leaky"


def test_frames_innermost_first_and_capped():
    store = _store(frames=2)

    def deep(n: int) -> None:
        if n == 0:
            raise RuntimeError("deep")
        deep(n - 1)

    _record(store, _raised(lambda: deep(5) or RuntimeError()))  # type: ignore[func-returns-value]
    detail = store.detail(_groups(store)[0]["id"])
    assert detail is not None and len(detail["frames"]) == 2
    assert all(f["methodName"].endswith("deep") for f in detail["frames"])  # the innermost two


def test_fingerprint_first_application_frame():
    a = _raised(lambda: RuntimeError("a"))
    b = _raised(lambda: RuntimeError("different message, same place"))
    assert fingerprint(a) == fingerprint(b)
    assert fingerprint(a).startswith("RuntimeError\n" + __name__ + ":_raised:")
    assert fingerprint(RuntimeError("never raised")) == "RuntimeError"  # no frames at all


def test_group_shape_and_location():
    store = _store()
    _record(store, _raised(lambda: RuntimeError("boom")), _request(), source="request", thread="worker-1")
    group = _groups(store)[0]
    assert tuple(group) == GROUP_KEYS
    assert len(group["id"]) == 16 and all(c in "0123456789abcdef" for c in group["id"])
    assert group["location"].startswith(f"{__name__}._raised(test_exceptions.py:")
    assert group["applicationException"] is True
    assert (group["lastThread"], group["lastRequestMethod"], group["lastRequestPath"]) == ("worker-1", "GET", "/x")
    assert (group["lastHandler"], group["lastSource"], group["lastTraceId"]) == ("app:x", "request", "r1")
    assert group["errorContract"] is None
    assert store.detail("unknown") is None


def test_builtins_prefix_dropped_and_qualname_kept():
    class Inner(Exception):
        pass

    store = _store()
    _record(store, _raised(lambda: Inner("x")))
    _record(store, _raised(lambda: OSError("y")))
    names = sorted(g["exceptionClassName"] for g in _groups(store))
    assert names == ["OSError", f"{__name__}.test_builtins_prefix_dropped_and_qualname_kept.<locals>.Inner"]


def test_cancelled_error_never_recorded():
    store = _store()
    _record(store, _raised(asyncio.CancelledError), _request(), source="request")
    _record(store, _raised(KeyboardInterrupt))
    assert store.report()["totalExceptions"] == 0


def _stdlib_file() -> str:
    return os.path.join(sysconfig.get_paths()["stdlib"], "json", "decoder.py")


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        (__file__, True),
        (os.path.join("C:" if os.name == "nt" else "/", "app", "main.py"), True),
        (os.path.join("venv", "lib", "site-packages", "starlette", "routing.py"), False),
        (os.path.join("usr", "lib", "python3", "dist-packages", "x.py"), False),
        ("<frozen importlib._bootstrap>", False),
        ("<string>", False),
    ],
    ids=["this-test", "app", "site-packages", "dist-packages", "frozen", "string"],
)
def test_is_application_frame_table(filename: str, expected: bool):
    assert is_application_frame(filename) is expected


def test_stdlib_and_sharpit_are_not_application():
    import sharpit.engine.capture.exceptions as own

    assert is_application_frame(_stdlib_file()) is False
    assert is_application_frame(_stdlib_file().upper() if os.name == "nt" else _stdlib_file()) is False
    assert is_application_frame(own.__file__) is False


def test_reentrant_log_while_locked_no_deadlock():
    # a GC finalizer that logs with exc_info while the store lock is held on this thread must not deadlock
    store = _store()
    inner = _raised(lambda: ValueError("from finalizer"))

    class Finalizer:
        def __del__(self) -> None:
            _record(store, inner)

    original = store._lock  # pyright: ignore[reportPrivateUsage]

    class Hook:
        def __enter__(self) -> None:
            original.acquire()
            Finalizer()  # collected at once: __del__ runs while the lock is held
            gc.collect()

        def __exit__(self, *_: object) -> None:
            original.release()

    store._lock = Hook()  # type: ignore[assignment]  # pyright: ignore[reportPrivateUsage]
    done = threading.Event()
    worker = threading.Thread(target=lambda: (_record(store, _raised(lambda: RuntimeError("outer"))), done.set()))
    worker.start()
    worker.join(5)
    assert done.is_set()
    store._lock = original  # pyright: ignore[reportPrivateUsage]
    assert [g["message"] for g in _groups(store)] == ["outer"]  # the re-entrant record was dropped


@pytest.mark.parametrize("operation", ["report", "detail", "set_status", "clear", "forget_request"])
def test_reentrant_log_while_reading_no_deadlock(operation: str, monkeypatch: pytest.MonkeyPatch):
    # every locked section, not only record(): a finalizer that logs while report() holds the lock must not deadlock
    from sharpit.engine.capture import exceptions as module

    store = _store()
    _record(store, _raised(lambda: RuntimeError("outer")))
    gid = _groups(store)[0]["id"]
    inner = SlotsError("from finalizer")  # refuses attributes: its mark needs the fallback lock too

    class Finalizer:
        def __del__(self) -> None:
            _record(store, inner)

    owner, name = (module, "_FALLBACK_LOCK") if operation == "forget_request" else (store, "_lock")
    original = getattr(owner, name)

    class Hook:
        def __enter__(self) -> None:
            original.acquire()
            Finalizer()
            gc.collect()

        def __exit__(self, *_: object) -> None:
            original.release()

    monkeypatch.setattr(owner, name, Hook())
    calls: dict[str, Callable[[], object]] = {
        "report": store.report,
        "detail": lambda: store.detail(gid),
        "set_status": lambda: store.set_status(gid, "RESOLVED"),
        "clear": store.clear,
        "forget_request": lambda: store.forget_request("r1"),
    }
    done = threading.Event()
    worker = threading.Thread(target=lambda: (calls[operation](), done.set()), daemon=True)
    worker.start()
    worker.join(5)
    assert done.is_set()


def test_fallback_keeps_no_reference_to_the_exception():
    # spec decision log: the fallback stores the id and the mark only; a strong reference keeps frames alive
    import sys

    exc = SlotsError("refuses attributes")
    before = sys.getrefcount(exc)
    mark_seen(exc, None, "_ref")
    assert sys.getrefcount(exc) == before


def test_capped_frames_keep_the_application_location():
    # location and applicationException come from the same uncapped walk as the fingerprint
    import json

    store = _store(frames=1)
    exc = _raised(lambda: json.loads("x"))
    _record(store, exc)
    group = _groups(store)[0]
    assert group["applicationException"] is True
    assert group["location"] is not None and group["location"].startswith(f"{__name__}.test_capped_frames")
    detail = store.detail(group["id"])
    assert detail is not None and len(detail["frames"]) == 1


def test_marks_are_per_store():
    # two installed contexts (or a leftover handler of an earlier app) each record the exception once
    first, second = _store(), _store()
    exc = _raised(lambda: RuntimeError("seen by both"))
    for store in (first, second):
        _record(store, exc, _request("r1"), source="log")
        _record(store, exc, _request("r1"), source="request")
    assert [s.report()["totalExceptions"] for s in (first, second)] == [1, 1]
    slots = SlotsError("no attributes")
    for store in (first, second):
        _record(store, slots, _request("r2"))
    assert [s.report()["totalExceptions"] for s in (first, second)] == [2, 2]
