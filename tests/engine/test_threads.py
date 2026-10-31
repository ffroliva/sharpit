"""Threads and asyncio tasks (F9, spec §7.9): inferred thread states, await-chain task stacks, the loop hand-off.

Derived cases: BootUI's ``ThreadDumpService`` reads JVM thread states; CPython has none, so sharpit infers them.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import sys
import threading
import time
from collections.abc import Callable, Coroutine, Iterator
from types import SimpleNamespace
from typing import Any

import pytest

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.capture.correlation import REQUEST, RequestInfo
from sharpit.engine.capture.streams import SSE_TASK
from sharpit.engine.collectors.threads import (
    BLOCKING_WAITS,
    FREE_THREADED,
    MAX_TASKS,
    NO_LOOP,
    REPORT_KEYS,
    TASK_KEYS,
    THREAD_KEYS,
    infer_state,
    task_info,
    task_stack,
    threads_report,
)
from sharpit.engine.tools import CallContext, call_tool
from sharpit.fastapi.adapter import SharpitHandle

_HANDLES: list[SharpitHandle] = []
SECRET = "hunter2-local-value"


@pytest.fixture(autouse=True)
def _uninstall() -> Iterator[None]:
    yield
    while _HANDLES:
        _HANDLES.pop().uninstall_capture()


def _ctx(**options: Any) -> Any:
    handle = install(FastAPI(), enabled="ON", show_banner=False, mcp_enabled="ON", **options)
    _HANDLES.append(handle)
    return handle.context


class LoopThread:
    """An event loop running in its own thread, like uvicorn's, so the test thread is an off-loop reader."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, name="test-loop", daemon=True)
        self.thread.start()

    def run[T](self, coro: Coroutine[Any, Any, T]) -> T:
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(5)

    def spawn(self, factory: Callable[[], Coroutine[Any, Any, Any]], name: str, **kw: Any) -> asyncio.Task[Any]:
        async def make() -> asyncio.Task[Any]:
            return asyncio.get_running_loop().create_task(factory(), name=name, **kw)

        return self.run(make())

    def close(self) -> None:
        async def cancel_all() -> None:
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        self.run(cancel_all())
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)
        self.loop.close()


@pytest.fixture
def loop_thread() -> Iterator[LoopThread]:
    lt = LoopThread()
    yield lt
    lt.close()


async def _forever() -> None:
    await asyncio.sleep(60)


def _names(report: dict[str, Any]) -> list[str]:
    return [t["name"] for t in report["tasks"]]


# --- thread states --------------------------------------------------------------------------------------------------


def _fake_frame(module: str, qualname: str) -> Any:
    return SimpleNamespace(
        f_globals={"__name__": module}, f_code=SimpleNamespace(co_qualname=qualname, co_filename=f"{module}.py")
    )


@pytest.mark.parametrize(("module", "qualname"), sorted(BLOCKING_WAITS))
def test_infer_state_table(module: str, qualname: str):
    assert infer_state([_fake_frame(module, qualname), _fake_frame("app", "work")]) == "WAITING"
    assert infer_state([_fake_frame("app", "work"), _fake_frame(module, qualname)]) == "RUNNABLE"  # innermost only


def test_infer_state_runnable_cases():
    assert infer_state([]) == "RUNNABLE"
    assert infer_state([_fake_frame("threading", "Thread.run")]) == "RUNNABLE"


@pytest.mark.parametrize("wait", ["event", "queue", "executor"])
def test_real_blocked_threads_waiting(wait: str):
    import queue  # noqa: PLC0415
    from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415

    event, q = threading.Event(), queue.Queue[int]()
    executor = ThreadPoolExecutor(1, thread_name_prefix="t8-idle")
    target: dict[str, Callable[[], object]] = {"event": lambda: event.wait(5), "queue": lambda: q.get(timeout=5)}
    if wait == "executor":
        executor.submit(lambda: None).result(5)
        name = next(t.name for t in threading.enumerate() if t.name.startswith("t8-idle"))
    else:
        name = f"t8-{wait}"
        threading.Thread(target=target[wait], name=name, daemon=True).start()
    try:
        deadline = time.monotonic() + 5
        while True:
            row = next(r for r in threads_report(_ctx(), name, None, None, None)["threads"] if r["name"] == name)
            if row["state"] == "WAITING" or time.monotonic() > deadline:
                break
            time.sleep(0.01)
        assert row["state"] == "WAITING", row["stackTrace"][:3]
    finally:
        event.set()
        q.put(1)
        executor.shutdown(wait=True)


def test_state_exact_filter():
    event = threading.Event()
    threading.Thread(target=event.wait, args=(5,), name="t8-filter", daemon=True).start()
    ctx = _ctx()
    try:
        time.sleep(0.05)
        waiting = threads_report(ctx, None, "waiting", None, None)
        assert "t8-filter" in [r["name"] for r in waiting["threads"]]
        assert {r["state"] for r in waiting["threads"]} == {"WAITING"}
        assert threads_report(ctx, None, "WAIT", None, None)["threads"] == []  # exact, not a substring
        named = threads_report(ctx, "T8-FILTER", None, None, None)
        assert [r["name"] for r in named["threads"]] == ["t8-filter"]
        assert named["page"]["total"] == threading.active_count()
        counts = {c["state"]: c["count"] for c in named["stateCounts"]}
        assert sum(counts.values()) == named["totalThreads"]
    finally:
        event.set()


# --- task stacks ----------------------------------------------------------------------------------------------------


async def _inner() -> None:
    await asyncio.sleep(60)


async def _middle() -> None:
    await _inner()


async def _outer() -> None:
    await _middle()


def _functions(stack: list[str]) -> list[str]:
    return [s.split(" (", 1)[0].rsplit(".", 1)[-1] for s in stack]


def test_task_stuck_in_nested_sleep_full_stack(loop_thread: LoopThread, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delattr(asyncio, "capture_call_graph", raising=False)  # the await-chain walk (Python < 3.14)
    task = loop_thread.spawn(_outer, "nested")
    loop_thread.run(asyncio.sleep(0.01))
    stack = task_stack(task, 64)
    assert _functions(stack) == ["sleep", "_inner", "_middle", "_outer"]
    assert stack[1].startswith("test_threads._inner (test_threads.py:")
    assert _functions(task_stack(task, 2)) == ["sleep", "_inner"]  # the innermost frames are kept


def test_task_stack_capture_call_graph_branch(loop_thread: LoopThread, monkeypatch: pytest.MonkeyPatch):
    task = loop_thread.spawn(_outer, "graph")
    loop_thread.run(asyncio.sleep(0.01))
    frame = sys._getframe()  # pyright: ignore[reportPrivateUsage]
    seen: list[object] = []

    def fake_graph(future: object) -> Any:
        seen.append(future)
        return SimpleNamespace(call_stack=(SimpleNamespace(frame=frame),) * 3)

    monkeypatch.setattr(asyncio, "capture_call_graph", fake_graph, raising=False)
    stack = task_stack(task, 2)
    assert seen == [task]
    assert _functions(stack) == ["test_task_stack_capture_call_graph_branch"] * 2


def test_cancelled_task_state_and_none_coro():
    def fake(cancelled: bool, done: bool, coro: object) -> Any:
        return SimpleNamespace(
            get_name=lambda: "fake",
            get_coro=lambda: coro,
            cancelled=lambda: cancelled,
            done=lambda: done,
            get_context=contextvars.copy_context,
        )

    assert task_info(fake(True, True, None), 8, names_only=False)["state"] == "CANCELLED"  # checked before done()
    assert task_info(fake(False, True, None), 8, names_only=False)["state"] == "DONE"
    row = task_info(fake(False, False, None), 8, names_only=False)
    assert (row["state"], row["coroutine"], row["stackTrace"], row["request"]) == ("PENDING", None, [], None)


# --- the loop hand-off ----------------------------------------------------------------------------------------------


def test_off_loop_reader_collects_on_loop(loop_thread: LoopThread):
    ctx = _ctx()
    ctx.capture.loop = loop_thread.loop
    loop_thread.spawn(_forever, "t8-sleeper")
    report = threads_report(ctx, None, None, None, None)  # from the test thread, not the loop thread
    (row,) = [t for t in report["tasks"] if t["name"] == "t8-sleeper"]
    assert (row["coroutine"], row["state"], row["request"]) == ("_forever", "PENDING", None)
    assert _functions(row["stackTrace"])[-1] == "_forever"
    assert report["taskCount"] == len(report["tasks"]) and report["warnings"] == []


def test_on_loop_reader_skips_itself():
    ctx = _ctx()

    async def main() -> dict[str, Any]:
        ctx.capture.loop = asyncio.get_running_loop()
        asyncio.get_running_loop().create_task(_forever(), name="t8-on-loop")
        await asyncio.sleep(0)
        return threads_report(ctx, None, None, None, None)

    report = asyncio.run(main())
    assert _names(report) == ["t8-on-loop"]  # the reading task itself is not listed


def test_no_loop_warning():
    ctx = _ctx()
    report = threads_report(ctx, None, None, None, None)
    assert (report["tasks"], report["taskCount"], report["warnings"]) == ([], 0, [NO_LOOP])
    closed = asyncio.new_event_loop()
    closed.close()
    ctx.capture.loop = closed  # a TestClient without `with` leaves a closed loop behind
    assert threads_report(ctx, None, None, None, None)["warnings"] == [NO_LOOP]


def test_sse_tasks_excluded(loop_thread: LoopThread):
    ctx = _ctx()
    ctx.capture.loop = loop_thread.loop
    sse = contextvars.copy_context()
    sse.run(SSE_TASK.set, True)
    loop_thread.spawn(_forever, "t8-sse", context=sse)
    loop_thread.spawn(_forever, "t8-plain")
    assert _names(threads_report(ctx, None, None, None, None)) == ["t8-plain"]


def test_task_request_link(loop_thread: LoopThread):
    ctx = _ctx()
    ctx.capture.loop = loop_thread.loop
    info = RequestInfo("r1", ctx.context_id, "GET", "/owners/1", None, time.perf_counter_ns() - 5_000_000, None)
    request_ctx = contextvars.copy_context()
    request_ctx.run(REQUEST.set, info)
    loop_thread.spawn(_forever, "t8-request", context=request_ctx)
    (row,) = threads_report(ctx, None, None, None, None)["tasks"]
    assert (row["request"]["method"], row["request"]["path"]) == ("GET", "/owners/1")
    assert row["request"]["ageMs"] >= 5
    assert tuple(row["request"]) == ("method", "path", "ageMs")


def test_free_threaded_names_only(loop_thread: LoopThread, monkeypatch: pytest.MonkeyPatch):
    ctx = _ctx()
    ctx.capture.loop = loop_thread.loop
    loop_thread.spawn(_forever, "t8-free")
    monkeypatch.setattr(sys, "_is_gil_enabled", lambda: False, raising=False)
    report = threads_report(ctx, None, None, None, None)
    assert report["warnings"] == [FREE_THREADED]
    assert all(r["stackTrace"] == [] and r["state"] == "UNKNOWN" for r in report["threads"])
    (row,) = report["tasks"]
    assert (row["name"], row["coroutine"], row["stackTrace"], row["request"]) == ("t8-free", None, [], None)


def test_metadata_only_hides_stacks(loop_thread: LoopThread):
    ctx = _ctx(expose_values="METADATA_ONLY")
    ctx.capture.loop = loop_thread.loop
    loop_thread.spawn(_forever, "t8-meta")
    report = threads_report(ctx, None, None, None, None)
    assert all(r["stackTrace"] == [] for r in report["threads"] + report["tasks"])
    assert _names(report) == ["t8-meta"]


def test_tasks_capped_500(loop_thread: LoopThread):
    ctx = _ctx()
    ctx.capture.loop = loop_thread.loop
    for n in range(MAX_TASKS + 10):
        loop_thread.spawn(_forever, f"t8-{n:04d}")
    report = threads_report(ctx, None, None, None, None)
    assert (len(report["tasks"]), report["taskCount"]) == (MAX_TASKS, MAX_TASKS + 10)


def test_mcp_limit_caps_tasks(loop_thread: LoopThread):
    ctx = _ctx()
    ctx.capture.loop = loop_thread.loop
    for n in range(5):
        loop_thread.spawn(_forever, f"t8-mcp-{n}")
    report = call_tool(CallContext(ctx, {}), "get_threads", {"limit": 2}, via="mcp")
    assert (len(report["tasks"]), report["taskCount"], len(report["threads"])) == (2, 5, 2)


def test_no_locals_or_args(loop_thread: LoopThread):
    ctx = _ctx()
    ctx.capture.loop = loop_thread.loop

    async def holder(argument: str) -> None:
        local = argument + "-local"  # noqa: F841 - a local value the report must never carry
        await asyncio.sleep(60)

    loop_thread.spawn(lambda: holder(SECRET), "t8-locals")
    event = threading.Event()

    def blocked(argument: str) -> None:
        event.wait(5)

    threading.Thread(target=blocked, args=(SECRET,), name="t8-locals-thread", daemon=True).start()
    try:
        assert SECRET not in json.dumps(threads_report(ctx, None, None, None, None))
    finally:
        event.set()


def test_shape_keys_match_bootui(loop_thread: LoopThread):
    # ThreadDumpReport, ThreadInfoDto, ThreadStateCountDto, PageMetadata record components, in order; tasks,
    # taskCount and warnings are sharpit's additions (spec §17)
    assert REPORT_KEYS == (
        "available", "unavailableReason", "capturedAt", "totalThreads", "daemonThreads", "peakThreads",
        "startedThreadCount", "virtualThreadsSupported", "cpuTimeSupported", "deadlockDetected", "deadlockedThreadIds",
        "stateCounts", "threads", "page", "tasks", "taskCount", "warnings",
    )  # fmt: skip
    assert THREAD_KEYS == (
        "id", "name", "state", "priority", "daemon", "virtual", "cpuTimeMillis", "userTimeMillis", "blockedCount",
        "waitedCount", "inNative", "suspended", "deadlocked", "lockName", "lockOwnerId", "lockOwnerName", "stackTrace",
    )  # fmt: skip
    assert TASK_KEYS == ("name", "coroutine", "state", "stackTrace", "request")
    ctx = _ctx()
    ctx.capture.loop = loop_thread.loop
    loop_thread.spawn(_forever, "t8-shape")
    report = threads_report(ctx, None, None, None, None)
    assert tuple(report) == REPORT_KEYS
    assert tuple(report["threads"][0]) == THREAD_KEYS and tuple(report["tasks"][0]) == TASK_KEYS
    assert tuple(report["stateCounts"][0]) == ("state", "count")
    assert tuple(report["page"]) == ("total", "matched", "offset", "limit", "returned", "hasMore")
