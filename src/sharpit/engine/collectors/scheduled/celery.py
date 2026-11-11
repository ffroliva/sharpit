"""Celery gatekeeper (observed through ``sys.modules``, never imported): an app's ``beat_schedule``.

Reading ``app.conf`` on an app that is not configured loads its configuration and may import a settings module (C0
spike, celery 5), so it is never done. A configured app's ``_conf`` is a ``ChainMap`` of plain dicts: the read is a
lookup. An unconfigured app with no configuration source pending (no ``config_from_object``/``config_from_envvar``,
no ``add_defaults``) is read from ``_preconf``, the plain dict that ``app.conf.<key> = ...`` writes to before loading.
Any other unconfigured app is named in a limitation.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from sharpit.engine.collectors.scheduled.model import (
    Discovery,
    Reader,
    as_dict,
    attrs,
    cron_field,
    fixed_rate,
    is_a,
    library_class,
    task,
)

_MS = timedelta(milliseconds=1)
_CRONTAB_FIELDS = ("_orig_minute", "_orig_hour", "_orig_day_of_month", "_orig_month_of_year", "_orig_day_of_week")
_NUMBER = (int, float)


def _solar(schedule: object) -> str | None:
    """``solar.__repr__``'s words, from its attributes: a daily event at a computed time has no rate or cron form."""
    values = attrs(schedule)
    event, lat, lon = values.get("event"), values.get("lat"), values.get("lon")
    if type(event) is str and type(lat) in _NUMBER and type(lon) in _NUMBER:
        return f"solar: {event} at latitude {lat}, longitude: {lon}"
    return None


def _entry_task(entry: Any, kinds: dict[type | None, str]) -> dict[str, Any]:
    name = entry.get("task")
    runnable = name if type(name) is str else None
    schedule: object = entry.get("schedule")
    kind = kinds.get(type(schedule))  # exact library types only: a subclass could run code on attribute access
    if kind == "crontab":
        fields = attrs(schedule)
        return task(runnable, "CRON", " ".join(cron_field(fields.get(key)) for key in _CRONTAB_FIELDS))
    if kind == "solar":
        return task(runnable, "ONE_SHOT", _solar(schedule))  # BootUI: a custom Trigger is ONE_SHOT + its text
    if kind == "schedule":
        schedule = attrs(schedule).get("run_every")
    if type(schedule) is timedelta:
        return fixed_rate(runnable, schedule // _MS)
    if type(schedule) is int or type(schedule) is float:
        return fixed_rate(runnable, round(schedule * 1000))
    return task(runnable, "ONE_SHOT")


def _beat_schedule(state: dict[str, Any]) -> tuple[bool, object]:
    """(readable, beat_schedule) without loading configuration."""
    if state.get("configured") is True:
        conf: Any = state.get("_conf")
        return True, (conf.get("beat_schedule") if is_a(conf, Mapping) else None)
    pending: Any = state.get("_pending_defaults")
    preconf = state.get("_preconf")
    if state.get("_config_source") is None and type(pending) is deque and not pending and type(preconf) is dict:
        return True, as_dict(preconf).get("beat_schedule")
    return False, None


def reader() -> Reader | None:
    app_type = library_class("celery.app.base", "Celery")
    if app_type is None:
        return None
    kinds = {library_class("celery.schedules", name): name for name in ("crontab", "schedule", "solar")}

    def read(label: str, value: object) -> Discovery | None:
        if not is_a(value, app_type):
            return None
        state = vars(value)
        readable, beat = _beat_schedule(state)
        if not readable:
            main = state.get("main")
            reason = f"Celery app {main if type(main) is str else '?'} not configured yet; reading beat_schedule"
            return Discovery(False, [], [f"{label}: {reason} would load its configuration"])
        return Discovery(True, [_entry_task(e, kinds) for e in as_dict(beat).values() if type(e) is dict])

    return read
