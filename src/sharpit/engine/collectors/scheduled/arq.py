"""arq gatekeeper (observed through ``sys.modules``, never imported): ``cron_jobs`` declared on a worker settings class.

A ``CronJob`` is a dataclass, read with ``vars()``. The expression is Spring's six fields (second minute hour day
month weekday), ``*`` for an unset field.
"""

from __future__ import annotations

from typing import Any

from sharpit.engine.collectors.scheduled.model import (
    Discovery,
    Reader,
    as_list,
    cron_field,
    is_a,
    library_class,
    qualified_name,
    task,
)

_FIELDS = ("second", "minute", "hour", "day", "month", "weekday")


def _cron_task(job: object) -> dict[str, Any]:
    fields = vars(job)
    expression = " ".join(cron_field(fields.get(key)) for key in _FIELDS)
    return task(qualified_name(fields.get("coroutine")), "CRON", expression)


def reader() -> Reader | None:
    cron_type = library_class("arq.cron", "CronJob")
    if cron_type is None:
        return None

    def read(_label: str, value: object) -> Discovery | None:
        if not is_a(value, type):  # a class, read through its own namespace (inherited cron_jobs are not read)
            return None
        crons = [job for job in as_list(vars(value).get("cron_jobs")) if is_a(job, cron_type)]
        return Discovery(True, [_cron_task(job) for job in crons]) if crons else None

    return read
