"""Threads and asyncio tasks panel (F9, spec §7.9): BootUI's ``ThreadDumpReport`` plus the app loop's tasks.

CPython has no thread state, so it is inferred from the innermost Python frame. Task stacks follow the await chain
(``Task.get_stack()`` returns one frame for a suspended coroutine). Only code names and line numbers are read: no
locals and no argument values, ever.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
import sys
import threading
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Literal

from sharpit.engine.capture.correlation import REQUEST
from sharpit.engine.capture.streams import SSE_TASK
from sharpit.engine.masking import MASK, Exposure, is_secret_value
from sharpit.engine.paging import paged

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

# (module, co_qualname) of the innermost Python frame of a thread blocked in a stdlib wait. Event.wait, Queue.get and
# Semaphore.acquire all end in Condition.wait; the lock acquire below it and time.sleep are C, with no frame.
BLOCKING_WAITS = frozenset(
    {
        ("threading", "Condition.wait"),
        ("threading", "Thread.join"),
        ("threading", "Thread._wait_for_tstate_lock"),  # Thread.join before 3.13
        ("selectors", "SelectSelector._select"),  # Windows
        ("selectors", "SelectSelector.select"),
        ("selectors", "PollSelector.select"),
        ("selectors", "EpollSelector.select"),
        ("selectors", "DevpollSelector.select"),
        ("selectors", "KqueueSelector.select"),
        ("asyncio.windows_events", "IocpProactor._poll"),  # an idle loop on Windows: the selector wait's equivalent
        ("concurrent.futures.thread", "_worker"),  # an idle executor worker, blocked in SimpleQueue.get
    }
)
MAX_TASKS = 500
LOOP_WAIT_SECONDS = 2.0
NO_LOOP = "No running event loop is known yet: tasks show after the app's startup or its first request"
LOOP_BUSY = f"The event loop did not answer within {LOOP_WAIT_SECONDS:g} s; tasks are not shown"
FREE_THREADED = "This is a free-threaded Python build: sharpit shows thread and task names only"
REPORT_KEYS = (
    "available", "unavailableReason", "capturedAt", "totalThreads", "daemonThreads", "peakThreads",
    "startedThreadCount", "virtualThreadsSupported", "cpuTimeSupported", "deadlockDetected", "deadlockedThreadIds",
    "stateCounts", "threads", "page", "tasks", "taskCount", "warnings",
)  # fmt: skip
THREAD_KEYS = (
    "id", "name", "state", "priority", "daemon", "virtual", "cpuTimeMillis", "userTimeMillis", "blockedCount",
    "waitedCount", "inNative", "suspended", "deadlocked", "lockName", "lockOwnerId", "lockOwnerName", "stackTrace",
)  # fmt: skip
TASK_KEYS = ("name", "coroutine", "state", "stackTrace", "request")


def _location(frame: Any) -> tuple[str, str]:
    return str(frame.f_globals.get("__name__", "?")), frame.f_code.co_qualname


def infer_state(frames: Sequence[Any]) -> Literal["RUNNABLE", "WAITING"]:
    """``WAITING`` when the innermost frame (``frames[0]``) is a known blocking wait, else ``RUNNABLE``."""
    return "WAITING" if frames and _location(frames[0]) in BLOCKING_WAITS else "RUNNABLE"


def _frame_text(frame: Any) -> str:
    module, function = _location(frame)
    return f"{module}.{function} ({os.path.basename(frame.f_code.co_filename)}:{frame.f_lineno})"


def _thread_frames(frame: Any, max_frames: int) -> list[Any]:
    frames: list[Any] = []
    while frame is not None and len(frames) < max_frames:
        frames.append(frame)
        frame = frame.f_back
    return frames


def task_stack(task: Any, max_frames: int) -> list[str]:
    """The task's await chain as frame strings, innermost first, at most ``max_frames``."""
    graph = getattr(asyncio, "capture_call_graph", None)  # 3.14+; looked up per call so a test can force either branch
    frames: list[Any] = []
    if graph is not None:
        captured = graph(task)
        frames = [entry.frame for entry in captured.call_stack] if captured is not None else []  # innermost first
    else:
        coro = task.get_coro()
        while coro is not None and len(frames) < 1000:  # a bound against a cyclic chain
            frame = (
                getattr(coro, "cr_frame", None) or getattr(coro, "gi_frame", None) or getattr(coro, "ag_frame", None)
            )
            if frame is not None:
                frames.append(frame)
            # a Future (or anything not a coroutine) ends the chain: it has none of these attributes
            coro = (
                getattr(coro, "cr_await", None)
                or getattr(coro, "gi_yieldfrom", None)
                or getattr(coro, "ag_await", None)
            )
        frames.reverse()
    return [_frame_text(f) for f in frames[:max_frames]]


def task_info(ctx: SharpitContext, task: Any, max_frames: int, *, names_only: bool) -> dict[str, Any]:
    """``AsyncTaskDto``; ``max_frames`` 0 gives an empty stack (``METADATA_ONLY``); the name is masked."""
    name = _thread_name(ctx, task.get_name())
    if names_only:
        return dict(zip(TASK_KEYS, (name, None, _task_state(task), [], None), strict=True))
    info = task.get_context().get(REQUEST)
    request = (
        None
        if info is None
        else {
            "method": info.method,
            "path": info.path,
            "ageMs": (time.perf_counter_ns() - info.started_ns) // 1_000_000,
        }
    )
    return {
        "name": name,
        "coroutine": getattr(task.get_coro(), "__qualname__", None),  # an eager task's coroutine can be None
        "state": _task_state(task),
        "stackTrace": task_stack(task, max_frames) if max_frames else [],
        "request": request,  # RequestInfo.path is masked by the capture middleware
    }


def _task_state(task: Any) -> str:
    return "CANCELLED" if task.cancelled() else "DONE" if task.done() else "PENDING"  # cancelled() first: also done


def _collect(ctx: SharpitContext, max_frames: int, cap: int, names_only: bool) -> tuple[list[dict[str, Any]], int]:
    """On the loop: every task but the reader itself and sharpit's own SSE streams."""
    me = asyncio.current_task()
    tasks = [t for t in asyncio.all_tasks() if t is not me and not t.get_context().get(SSE_TASK, False)]
    tasks.sort(key=lambda t: t.get_name())
    return [task_info(ctx, t, max_frames, names_only=names_only) for t in tasks[:cap]], len(tasks)


def _tasks(
    ctx: SharpitContext, max_frames: int, cap: int, names_only: bool
) -> tuple[list[dict[str, Any]], int, str | None]:
    loop = ctx.capture.loop
    if loop is None or loop.is_closed() or not loop.is_running():
        return [], 0, NO_LOOP
    try:
        running: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is loop:
        return (*_collect(ctx, max_frames, cap, names_only), None)

    async def collect() -> tuple[list[dict[str, Any]], int]:  # NOSONAR - all_tasks() is only safe on the loop thread
        return _collect(ctx, max_frames, cap, names_only)

    future = asyncio.run_coroutine_threadsafe(collect(), loop)  # all_tasks() is only safe on the loop's own thread
    try:
        return (*future.result(LOOP_WAIT_SECONDS), None)
    except concurrent.futures.TimeoutError:
        future.cancel()
        return [], 0, LOOP_BUSY


def _thread_name(ctx: SharpitContext, name: str) -> str:
    """BootUI ``maskName``: a secret-looking name is masked; under ``METADATA_ONLY`` too (a name is metadata)."""
    shown = ctx.masker.mask_text(name)
    return shown if shown is not None else MASK if ctx.settings.mask_secrets and is_secret_value(name) else name


def threads_report(
    ctx: SharpitContext, q: str | None, state: str | None, offset: int | None, limit: int | None
) -> dict[str, Any]:
    """``ThreadDumpReport`` keys plus ``tasks``, ``taskCount`` and ``warnings``; ``limit`` also caps ``tasks``."""
    names_only = not getattr(sys, "_is_gil_enabled", lambda: True)()  # 3.13+; free-threaded builds are unsupported
    hide = names_only or ctx.settings.expose_values is Exposure.METADATA_ONLY  # BootUI: no stacks under METADATA_ONLY
    max_frames = 0 if hide else ctx.settings.threads_max_stack_frames
    # the state is metadata, so frames are read under METADATA_ONLY too; max_frames 0 hides only the stack text
    current: dict[int, Any] = {} if names_only else sys._current_frames()  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    rows: list[dict[str, Any]] = []
    for thread in threading.enumerate():
        frames = _thread_frames(current.get(thread.ident or 0), max(max_frames, 1))
        values = (
            thread.ident or 0,
            _thread_name(ctx, thread.name),
            "UNKNOWN" if names_only else infer_state(frames),
            0, thread.daemon, False, None, None, 0, 0, False, False, False, None, None, None,
            [_frame_text(f) for f in frames[:max_frames]],
        )  # fmt: skip
        rows.append(dict(zip(THREAD_KEYS, values, strict=True)))
    rows.sort(key=lambda r: r["id"])
    tally: dict[str, int] = {}
    for row in rows:
        tally[row["state"]] = tally.get(row["state"], 0) + 1
    wanted = (state or "").strip().lower()
    filtered = [r for r in rows if not wanted or r["state"].lower() == wanted]  # exact, as BootUI matchesState
    page, meta = paged(filtered, q, offset, limit, lambda r: [r["name"], r["state"], *r["stackTrace"]])
    meta["total"] = len(rows)  # BootUI counts every thread, before the state filter
    cap = MAX_TASKS if limit is None else min(MAX_TASKS, max(limit, 1))  # paged clamps limit to at least 1 too
    tasks, task_count, warning = _tasks(ctx, max_frames, cap, names_only)
    warnings = [w for w in (FREE_THREADED if names_only else None, warning) if w is not None]
    values = (
        True, None, round(time.time() * 1000), len(rows), sum(r["daemon"] for r in rows), len(rows), len(rows),
        False, False, False, list[int](), [{"state": s, "count": n} for s, n in sorted(tally.items())], page, meta,
        tasks, task_count, warnings,
    )  # fmt: skip
    return dict(zip(REPORT_KEYS, values, strict=True))
