"""APScheduler gatekeeper (observed through ``sys.modules``, never imported).

APScheduler 3: the jobs of ``MemoryJobStore`` stores and the pending jobs of a scheduler not started yet. Any other
store (SQLAlchemy, Redis, MongoDB, ...) is named in a limitation and never touched, since listing it is I/O.
APScheduler 4: reported, never read; its data-store API is asynchronous (C0 spike, 2026-11-11).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sharpit.engine.collectors.scheduled.model import (
    Discovery,
    Reader,
    as_dict,
    as_list,
    attrs,
    exact,
    fixed_rate,
    interval_unit,
    is_a,
    library_class,
    qualified_name,
    task,
)

_MS = timedelta(milliseconds=1)


def _entries(value: Any) -> list[Any]:
    """The first item of each tuple in a list (``_pending_jobs`` and ``MemoryJobStore._jobs`` hold tuples)."""
    return [entry[0] for entry in as_list(value) if type(entry) is tuple and entry]


def _job_task(job: Any, triggers: dict[type | None, str]) -> dict[str, Any]:
    # exact library types only: a host subclass could run code on attribute access or str()
    runnable = qualified_name(getattr(job, "func", None))
    trigger: object = getattr(job, "trigger", None)
    kind = triggers.get(type(trigger))
    if kind == "CRON":
        return task(runnable, "CRON", str(trigger))
    if kind == "INTERVAL":
        return fixed_rate(runnable, getattr(trigger, "interval") // _MS)  # noqa: B009 - a slot of IntervalTrigger
    if kind == "DATE":
        return task(runnable, "ONE_SHOT", None, None, interval_unit(None, None))
    return task(runnable, "ONE_SHOT")


def _jobs(label: str, state: dict[str, Any], memory: type | None) -> tuple[list[Any], list[str]]:
    """Pending jobs (added before start(): no store holds them yet) and in-memory store jobs; other stores skipped."""
    jobs = _entries(state.get("_pending_jobs"))
    skipped: list[str] = []
    for alias, store in as_dict(state.get("_jobstores")).items():
        if exact(store, memory):
            jobs.extend(_entries(attrs(store).get("_jobs")))
        else:
            name = alias if type(alias) is str else "?"
            skipped.append(
                f"{label}: job store {name} ({type(store).__qualname__}) not read; only in-memory stores are read"
            )
    return jobs, skipped


def reader() -> Reader | None:
    base = library_class("apscheduler.schedulers.base", "BaseScheduler")
    aps4 = [
        cls
        for cls in (
            library_class("apscheduler._schedulers.sync", "Scheduler"),
            library_class("apscheduler._schedulers.async_", "AsyncScheduler"),
        )
        if cls is not None
    ]
    if base is None and not aps4:
        return None
    memory = library_class("apscheduler.jobstores.memory", "MemoryJobStore")
    job_type = library_class("apscheduler.job", "Job")
    triggers = {
        library_class("apscheduler.triggers.cron", "CronTrigger"): "CRON",
        library_class("apscheduler.triggers.interval", "IntervalTrigger"): "INTERVAL",
        library_class("apscheduler.triggers.date", "DateTrigger"): "DATE",
    }

    def read(label: str, value: object) -> Discovery | None:
        if any(is_a(value, cls) for cls in aps4):
            return Discovery(
                False, [], [f"{label}: APScheduler 4 scheduler not read (its data store API is asynchronous)"]
            )
        if not is_a(value, base):
            return None
        jobs, skipped = _jobs(label, vars(value), memory)
        return Discovery(True, [_job_task(job, triggers) for job in jobs if exact(job, job_type)], skipped)

    return read
