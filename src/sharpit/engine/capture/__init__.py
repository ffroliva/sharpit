"""Framework-free capture state (spec §6): one ``CaptureState`` per installed context, filled task by task."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:  # later tasks add these modules; the adapter owns the wiring
    from sharpit.engine.capture.exceptions import ExceptionStore
    from sharpit.engine.capture.exchanges import HttpExchangeBuffer
    from sharpit.engine.capture.journal import RuntimeJournal
    from sharpit.engine.capture.logtail import LogTailBuffer
    from sharpit.engine.capture.sqltrace import SqlTraceRecorder  # pyright: ignore[reportMissingImports, reportUnknownVariableType]
    from sharpit.engine.capture.streams import ChangeStream, StreamSlots
    from sharpit.engine.sqla import EngineRegistry  # pyright: ignore[reportMissingImports, reportUnknownVariableType]


class CaptureHooks(Protocol):
    """The port the engine reports hook failures through; the adapter's ``CaptureWiring`` implements it."""

    def hook_failed(self, hook: str, exc: BaseException) -> None: ...


class Suspendable(Protocol):
    name: str

    def suspend(self) -> None: ...

    def resume(self) -> None: ...


class HookRegistry:
    """Engine-owned, insertion-ordered set of installed capture hooks."""

    def __init__(self) -> None:
        self._hooks: dict[str, Suspendable] = {}
        self.failures: list[str] = []  # the last suspend/resume's per-hook failures, as ``name: Type: message``

    def register(self, hook: Suspendable) -> None:
        self._hooks[hook.name] = hook

    def hooks(self) -> tuple[Suspendable, ...]:
        return tuple(self._hooks.values())

    def suspend(self) -> None:
        self._each(reversed(self.hooks()), "suspend")

    def resume(self) -> None:
        self._each(self.hooks(), "resume")

    def discard(self) -> None:
        self._each(self.hooks(), "discard", reset=False)

    def _each(self, hooks: Iterable[Suspendable], action: str, *, reset: bool = True) -> None:
        """Run ``action`` on every hook; one hook's failure is recorded and the rest carry on (as BootUI)."""
        if reset:
            self.failures = []
        for hook in hooks:
            try:
                method = getattr(hook, action, None)
                if method is not None:
                    method()
            except Exception as exc:  # noqa: BLE001 - a failing hook never strands the others
                self.failures.append(f"{hook.name}: {type(exc).__name__}: {exc}")


@dataclass(eq=False)
class CaptureState:
    exchanges: HttpExchangeBuffer | None = None
    exceptions: ExceptionStore | None = None
    sql_trace: SqlTraceRecorder | None = None
    log_tail: LogTailBuffer | None = None
    journal: RuntimeJournal | None = None
    stream_slots: StreamSlots | None = None
    engine_registry: EngineRegistry | None = None
    raw_sqlite_seen: bool = False
    loop: asyncio.AbstractEventLoop | None = None
    wiring: CaptureHooks | None = None
    hooks: HookRegistry = field(default_factory=HookRegistry)
    suspended_sources: set[str] = field(default_factory=set[str])  # SQL sources a suspended hook stops routing here
    activity_changes: ChangeStream | None = None
    # 0.4.0 slots (lane F), inert until their lanes fill them
    security_logs: Any | None = None  # B-security-logs' bounded audit buffer
    transactions: object | None = None  # A-transactions' recorder
    teardowns: list[Callable[[], None]] = field(default_factory=list[Callable[[], None]])  # run by uninstall (R17)
    # lanes' hooks: each returns its remover, or None to be retried (SQLAlchemy not imported yet); re-run after every
    # lifespan restart, their removers go to ``teardowns``
    attachers: list[Callable[[], Callable[[], None] | None]] = field(
        default_factory=list[Callable[[], Callable[[], None] | None]]
    )


def route_path(scope: Mapping[str, Any]) -> str:
    """Path below ``root_path`` (as Starlette's private ``get_route_path``): ``""`` for the bare mount path.

    Shared by ``SharpitMount``, the capture middleware's self-exclusion and the probe, so all three agree.
    """
    path: str = scope["path"]
    root_path: str = scope.get("root_path", "")
    if root_path and (path == root_path or path.startswith(root_path + "/")):
        return path[len(root_path) :]
    return path


def under(path: str, prefix: str) -> bool:
    """True when ``path`` is ``prefix`` itself or below it."""
    return path == prefix or path.startswith(prefix + "/")
