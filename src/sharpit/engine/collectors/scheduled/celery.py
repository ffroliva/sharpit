"""Celery gatekeeper (observed through ``sys.modules``, never imported): an app's ``beat_schedule``.

Only an app that is already configured is read. Reading ``app.conf`` on one that is not loads its configuration and
may import a settings module (C0 spike, celery 5), so such an app is named in a limitation instead. A configured app's
``_conf`` is a ``ChainMap`` of plain dicts: the read is a lookup.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from sharpit.engine.collectors.scheduled.model import (
    Discovery,
    Reader,
    as_dict,
    attrs,
    cron_field,
    exact,
    fixed_rate,
    is_a,
    library_class,
    task,
)

_MS = timedelta(milliseconds=1)
_CRONTAB_FIELDS = ("_orig_minute", "_orig_hour", "_orig_day_of_month", "_orig_month_of_year", "_orig_day_of_week")


def reader() -> Reader | None:
    app_type = library_class("celery.app.base", "Celery")
    if app_type is None:
        return None
    crontab = library_class("celery.schedules", "crontab")
    every = library_class("celery.schedules", "schedule")

    def entry_task(entry: Any) -> dict[str, Any]:
        name = entry.get("task")
        runnable = name if type(name) is str else None
        schedule: Any = entry.get("schedule")
        if exact(schedule, crontab):
            fields = attrs(schedule)
            return task(runnable, "CRON", " ".join(cron_field(fields.get(key)) for key in _CRONTAB_FIELDS))
        if exact(schedule, every):
            schedule = attrs(schedule).get("run_every")
        if type(schedule) is timedelta:
            return fixed_rate(runnable, schedule // _MS)
        if type(schedule) in (int, float):
            return fixed_rate(runnable, round(schedule * 1000))
        return task(runnable, "ONE_SHOT")

    def read(label: str, value: object) -> Discovery | None:
        if not is_a(value, app_type):
            return None
        state = vars(value)
        if state.get("configured") is not True:
            main = state.get("main")
            name = main if type(main) is str else "?"
            reason = (
                f"{label}: Celery app {name} not configured yet; reading beat_schedule would load its configuration"
            )
            return Discovery(False, [], [reason])
        conf: Any = state.get("_conf")
        beat: Any = conf.get("beat_schedule") if is_a(conf, Mapping) else None
        return Discovery(True, [entry_task(e) for e in as_dict(beat).values() if type(e) is dict])

    return read
