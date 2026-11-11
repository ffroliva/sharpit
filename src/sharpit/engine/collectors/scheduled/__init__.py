"""Scheduled tasks of in-process schedulers (``ScheduledTasksService`` and its providers, BootUI 2.3.0).

Discovery is a shallow walk of the app's own loaded modules: ``vars(module)`` and ``type(value)`` only, so a lazy
proxy is never evaluated. Each scheduler library has its own gatekeeper module; a store or app whose listing would do
I/O or load configuration is skipped with a limitation (proposed deviation D7: BootUI's DTO has no field for them).

Not discovered (D7d): a scheduler that is not a module global of the app's own modules, for example one created
inside a lifespan or a function, kept on ``app.state``, or held inside a dict, list or other object attribute.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from types import ModuleType
from typing import TYPE_CHECKING, Any

from sharpit.engine.collectors.scheduled import apscheduler, arq, celery
from sharpit.engine.collectors.scheduled.model import Discovery, Reader

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

__all__ = ["Discovery", "app_modules", "build_report", "discover", "scheduled_report"]


def build_report(discovery: Discovery | None) -> dict[str, Any]:
    """``ScheduledTasksService.report``: absent without an available source, else sorted by runnable, nulls last."""
    if discovery is None or not discovery.present:
        return {"schedulingPresent": False, "total": 0, "tasks": []}
    tasks = sorted(discovery.tasks, key=lambda t: (t["runnable"] is None, t["runnable"] or ""))
    return {"schedulingPresent": True, "total": len(tasks), "tasks": tasks}


def _read(readers: list[Reader], label: str, value: object) -> Discovery | None:
    for read in readers:
        try:
            part = read(label, value)
        except Exception as exc:  # noqa: BLE001 - an odd scheduler state: degrade; never crash the host
            return Discovery(False, [], [f"{label}: not read ({type(exc).__name__})"])
        if part is not None:
            return part
    return None


def discover(modules: Iterable[ModuleType]) -> Discovery:
    readers = [r for r in (apscheduler.reader(), celery.reader(), arq.reader()) if r is not None]
    found = Discovery(False)
    seen: set[int] = set()  # a scheduler imported into several modules is read once
    for module in modules if readers else ():
        namespace = vars(module)
        for name, value in tuple(namespace.items()):
            if id(value) in seen:
                continue
            seen.add(id(value))
            part = _read(readers, f"{namespace.get('__name__')}.{name}", value)
            if part is not None:
                found.present = found.present or part.present
                found.tasks.extend(part.tasks)
                found.limitations.extend(part.limitations)
    return found


def app_modules(ctx: SharpitContext) -> list[ModuleType]:
    """The app's loaded modules: the top-level package of ``app_package`` (else install()'s caller), and that root."""
    root = ctx.settings.app_package or ctx.caller_module
    top = (root or "sharpit").partition(".")[0]
    if top == "sharpit":
        return []
    return [
        module
        for name, module in tuple(sys.modules.items())
        if type(module) is ModuleType and (name == root or name.partition(".")[0] == top)
    ]


def scheduled_report(ctx: SharpitContext) -> dict[str, Any]:
    return build_report(discover(app_modules(ctx)))
