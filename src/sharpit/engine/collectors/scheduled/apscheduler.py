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


_CRON = "apscheduler.triggers.cron"
_WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")  # APScheduler numbers Monday 0; Spring takes names
_SPRING_FIELDS = ("second", "minute", "hour", "day", "month", "day_of_week")
_EXPRESSIONS = {
    "AllExpression": "all",
    "RangeExpression": "range",
    "MonthRangeExpression": "range",
    "WeekdayRangeExpression": "weekday",
    "LastDayOfMonthExpression": "last",
}  # WeekdayPositionExpression ("2nd fri") has no Spring day-of-month form: the trigger maps to ONE_SHOT


def _cron_kinds() -> dict[type | None, str]:
    """CronTrigger's field and expression classes (exact types: their attributes are read with ``vars()``)."""
    fields = {library_class(f"{_CRON}.fields", name): "field" for name in ("BaseField", "DayOfMonthField",
              "DayOfWeekField", "MonthField", "WeekField")}  # fmt: skip
    return fields | {library_class(f"{_CRON}.expressions", name): kind for name, kind in _EXPRESSIONS.items()}


def _range(first: int, last: object, weekday: bool) -> str | None:
    bounds = (first, last) if type(last) is int and last != first else (first,)
    if weekday and any(n not in range(7) for n in bounds):
        return None
    return "-".join(_WEEKDAYS[n] if weekday else str(n) for n in bounds)


def _expression(expr: object, weekday: bool, kinds: dict[type | None, str]) -> str | None:
    """One APScheduler cron expression in Spring syntax, built from its attributes (never its ``__str__``)."""
    kind = kinds.get(type(expr))
    values = attrs(expr) if kind not in (None, "field") else {}
    step = values.get("step")
    suffix = f"/{step}" if type(step) is int and step else ""
    first = values.get("first")
    if kind == "all":
        return ("MON" if weekday and suffix else "*") + suffix  # "*/2" counts from Monday in APScheduler
    if kind == "last":
        return "L"
    if kind in ("range", "weekday") and type(first) is int:
        text = _range(first, values.get("last"), weekday or kind == "weekday")
        return None if text is None else text + suffix
    return None


def _is_every(expressions: list[Any], kinds: dict[type | None, str]) -> bool:
    return len(expressions) == 1 and _expression(expressions[0], False, kinds) == "*"


def spring_cron(trigger: object, kinds: dict[type | None, str]) -> str | None:
    """Spring's six fields (second minute hour day month day-of-week); None when a field has no Spring form."""
    fields: dict[object, list[Any]] = {}
    field: object
    for field in as_list(getattr(trigger, "fields", None)):  # a slot of CronTrigger (exact type, matched by the caller)
        if kinds.get(type(field)) != "field":
            return None
        values = attrs(field)
        fields[values.get("name")] = as_list(values.get("expressions"))
    if not all(_is_every(fields.get(name, []), kinds) for name in ("year", "week")):
        return None  # Spring has no year or ISO-week field
    parts: list[str] = []
    for name in _SPRING_FIELDS:
        texts = [_expression(e, name == "day_of_week", kinds) for e in fields.get(name, [])]
        if not texts or None in texts:
            return None
        parts.append(",".join(t for t in texts if t is not None))
    return " ".join(parts)


def _job_task(job: Any, triggers: dict[type | None, str]) -> dict[str, Any]:
    # exact library types only: a host subclass could run code on attribute access or str()
    runnable = qualified_name(getattr(job, "func", None))
    trigger: object = getattr(job, "trigger", None)
    kind = triggers.get(type(trigger))
    expression = spring_cron(trigger, _cron_kinds()) if kind == "CRON" else None
    if expression is not None:
        return task(runnable, "CRON", expression)
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
