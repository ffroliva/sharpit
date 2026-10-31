"""Health panel (F8, spec §7.8): engine pings and user checks, run only on ``POST {api}/health/check``.

A GET returns the cached tree; before the first run every component is ``UNKNOWN``. Python cannot stop a thread, so a
check's deadline is a wait limit: a timed-out check is ``DOWN`` and single-flight stays held until its thread returns.
"""

from __future__ import annotations

import asyncio
import contextvars
import inspect
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from sharpit.engine import sqla
from sharpit.engine.daemon_executor import DaemonExecutor
from sharpit.engine.masking import MASK, is_sensitive_key
from sharpit.engine.singleflight import ActionBusy, Flight, SingleFlight

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

OPERATION = "health-check"
STATUSES = ("DOWN", "OUT_OF_SERVICE", "UP", "UNKNOWN")  # Spring's default aggregation order, most severe first
DISABLED_REASON = "Nothing to check: no database engine is registered and no health check is configured"
ENGINES_ONLY_REASON = "Only database pings are configured; add your own checks with health_checks={...}"
NEVER_CHECKED = "Never checked; open the Health panel"
_ENGINES_STEP = {
    "title": "Register your database engines",
    "description": "sharpit pings each engine with the dialect's own ping (the one behind pool_pre_ping).",
    "snippets": ["sharpit.install(app, engines=[engine])"],
}
_CHECKS_STEP = {
    "title": "Add your own health checks",
    "description": "A check takes no arguments and returns True/False, a status string or a dict; raising means DOWN.",
    "snippets": ['sharpit.install(app, health_checks={"cache": lambda: cache.ping()})'],
}
_MAX_DETAIL = 1000


def node(
    name: str,
    status: str,
    details: object = None,
    components: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """``HealthNodeDto``."""
    return {
        "name": name,
        "status": status,
        "details": details,
        "components": components or [],
        "available": True,
        "unavailableReason": None,
        "guidanceReason": None,
        "setup": [],
        **extra,
    }


def aggregate(statuses: list[str]) -> str:
    """The most severe status (``DOWN`` > ``OUT_OF_SERVICE`` > ``UP`` > ``UNKNOWN``); none at all is ``UNKNOWN``."""
    ranked = [s for s in STATUSES if s in statuses]
    return ranked[0] if ranked else "UNKNOWN"


def _now_ms() -> int:
    return int(time.time() * 1000)


class HealthService:
    def __init__(self, ctx: SharpitContext) -> None:
        self._ctx = ctx
        self._last: dict[str, Any] | None = None
        self._executor: DaemonExecutor | None = None
        self._executor_lock = threading.Lock()

    # --- tree ---------------------------------------------------------------------------------------------------

    def _engines(self) -> list[tuple[str, Any]]:
        registry = self._ctx.capture.engine_registry
        return registry.engines() if registry is not None else []

    def _pending(self, engines: list[tuple[str, Any]]) -> dict[str, Any]:
        components: list[dict[str, Any]] = []
        if engines:
            components.append(node("db", "UNKNOWN", None, [node(name, "UNKNOWN") for name, _ in engines]))
        components += [node(name, "UNKNOWN") for name in self._ctx.health_checks]
        return node("application", "UNKNOWN", None, components)

    def _disabled(self) -> dict[str, Any]:
        return node(
            "application", "DISABLED", available=False, unavailableReason=DISABLED_REASON,
            setup=[_ENGINES_STEP, _CHECKS_STEP],
        )  # fmt: skip

    @property
    def last_status(self) -> str | None:
        """The root status of the last run, or None before the first one (activity's ``healthStatus``)."""
        last = self._last
        return last["status"] if last is not None else None

    def report(self, *, for_mcp: bool = False) -> dict[str, Any]:
        """The cached tree; never runs a check (spec §7.8: a GET opens no socket and runs no user code)."""
        last = self._last
        if last is None:
            engines = self._engines()
            if not engines and not self._ctx.health_checks:
                return self._disabled()
            root = self._pending(engines)
            if for_mcp:
                return {**root, "guidanceReason": NEVER_CHECKED}
        else:
            root = last
        return _with_guidance(root)

    # --- checks ---------------------------------------------------------------------------------------------------

    def _pool(self) -> DaemonExecutor:
        """sharpit's own 2 threads, created on the first check: never anyio's limiter the host's endpoints share."""
        with self._executor_lock:
            if self._executor is None:
                self._executor = DaemonExecutor(2, thread_name_prefix="sharpit-health")
            return self._executor

    async def check(self) -> dict[str, Any]:
        """Run every check (single-flight, held until every worker thread returns) and cache the tree."""
        single = self._ctx.lazy(f"singleflight:{OPERATION}", SingleFlight)
        release = single.try_acquire(OPERATION)
        if release is None:
            raise ActionBusy(OPERATION, single.active)
        flight = Flight(release)
        try:
            engines = self._engines()
            checks = dict(self._ctx.health_checks)
            if not engines and not checks:
                return self._disabled()
            executor = self._pool()
            pings = [self._ping(name, engine, flight, executor) for name, engine in engines]
            runs = [self._run(name, fn, flight, executor) for name, fn in checks.items()]
            results = await asyncio.gather(*pings, *runs)
            components: list[dict[str, Any]] = []
            if engines:
                children = list(results[: len(pings)])
                components.append(node("db", aggregate([c["status"] for c in children]), None, children))
            components += results[len(pings) :]
            root = node("application", aggregate([c["status"] for c in components]), None, components)
            self._last = root
            return _with_guidance(root)
        finally:
            flight.done()

    def _timed_out(self) -> str:
        return f"timed out after {self._ctx.settings.health_timeout:g}s; still running"

    def _failure(self, exc: BaseException) -> str | None:
        return self._ctx.masker.mask_text(f"{type(exc).__name__}: {exc}")

    async def _ping(self, name: str, engine: Any, flight: Flight, executor: DaemonExecutor) -> dict[str, Any]:
        details: dict[str, Any] = {"database": engine.dialect.name, "validationQuery": "dialect ping"}
        try:
            ok = await sqla.run_db_read(
                engine,
                lambda c: c.dialect.do_ping(c.connection.dbapi_connection),
                self._ctx.settings.health_timeout,
                executor=executor,
                done=flight.worker(),
            )
            status = "UP" if ok is not False else "DOWN"
        except TimeoutError:
            status, details["error"] = "DOWN", self._timed_out()
        except Exception as exc:  # noqa: BLE001 - a failed ping is this engine's DOWN, never the request's 500
            status, details["error"] = "DOWN", self._failure(exc)
        return node(name, status, {**details, "checkedAt": _now_ms()})

    async def _run(
        self, name: str, fn: Callable[[], object], flight: Flight, executor: DaemonExecutor
    ) -> dict[str, Any]:
        done = flight.worker()
        work = None
        try:
            async with asyncio.timeout(self._ctx.settings.health_timeout):
                work = executor.submit(contextvars.copy_context().run, fn)
                # fires when the thread returns, or at once when the queued call is cancelled before it starts
                work.add_done_callback(lambda _work: done())
                result = await asyncio.wrap_future(work)
                if inspect.isawaitable(result):  # an async __call__ or a sync wrapper returning a coroutine
                    result = await result
            status, details = self._interpret(result)
        except TimeoutError:
            status, details = "DOWN", {"error": self._timed_out()}
        except Exception as exc:  # noqa: BLE001 - a raising check is DOWN with its masked class and message
            status, details = "DOWN", {"error": self._failure(exc)}
        finally:
            if work is None:  # never submitted: no thread will call it
                done()
        return node(name, status, {**details, "checkedAt": _now_ms()})

    def _interpret(self, result: object) -> tuple[str, dict[str, Any]]:
        """``True``/``False``, a status string, or ``{"status": ..., **details}`` -> (status, masked details)."""
        if isinstance(result, bool):
            return ("UP" if result else "DOWN"), {}
        details: dict[str, Any] = {}
        raw: object = result
        if isinstance(result, dict):
            items = dict(cast("dict[object, object]", result))
            raw = items.pop("status", None)
            details = cast("dict[str, Any]", self._mask(items))
        status = raw.strip().upper() if isinstance(raw, str) else None
        if status in STATUSES:
            return status, details
        shown = (self._ctx.masker.mask_text(repr(raw)) or "")[:_MAX_DETAIL]  # mask first: a cut token escapes
        return "UNKNOWN", {**details, "error": f"unknown health status {shown}"}

    def _mask(self, value: object, key: str = "") -> object:
        """Keys through ``is_sensitive_key``, strings through ``mask_text``, containers walked (spec §7.8)."""
        masker = self._ctx.masker
        if key and is_sensitive_key(key):
            shown, masked = masker.mask(key, "")  # decided by the key alone: MASK, hidden, or shown (FULL)
            if masked or shown is None:
                return MASK if masked else None
        if isinstance(value, dict):
            items = cast("dict[object, object]", value).items()
            return {str(k): self._mask(v, str(k)) for k, v in items}
        if isinstance(value, list | tuple | set | frozenset):
            return [self._mask(v) for v in cast("list[object]", list(cast("Any", value)))]
        if isinstance(value, str):
            return masker.mask_text(value)
        if value is None or isinstance(value, bool | int | float):
            return masker.mask("", value)[0]  # a JSON scalar carries no text to leak; hidden under METADATA_ONLY
        text = masker.mask_text(repr(value))
        return text[:_MAX_DETAIL] if text is not None else None


def _with_guidance(root: dict[str, Any]) -> dict[str, Any]:
    """Port of BootUI ``HealthService.hasOnlyDefaultContributors``: only healthy engine pings -> nudge to add checks."""
    found: list[dict[str, Any]] = []

    def walk(nodes: list[dict[str, Any]]) -> None:
        for n in nodes:
            found.append(n)
            walk(n["components"])

    walk(root["components"])
    db = next((c for c in root["components"] if c["name"] == "db"), None)
    only_engines = db is not None and len(root["components"]) == 1
    healthy = all(n["status"] in ("UP", "UNKNOWN") for n in (root, *found))
    if only_engines and healthy and found:
        return {**root, "guidanceReason": ENGINES_ONLY_REASON, "setup": [_CHECKS_STEP]}
    return root


def health_service(ctx: SharpitContext) -> HealthService:
    return ctx.lazy("health", lambda: HealthService(ctx))
