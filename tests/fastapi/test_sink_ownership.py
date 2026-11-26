"""Which stack frames a request owns: its endpoint and its dependencies, never the work it hands off (D1).

A raw ASGI middleware puts the scope in a context variable; each case calls ``probe()`` where the work runs, and the
probe records ``owned(scope)``. No annotation here is postponed: FastAPI resolves the dependencies the cases define
inside their builders from the live signature.
"""

import asyncio
import functools
import os
import sys
import threading
from collections.abc import Callable, Iterator
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import anyio
import anyio.to_thread
import pytest
from fastapi.testclient import TestClient
from starlette.endpoints import HTTPEndpoint
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from fastapi import BackgroundTasks, Depends, FastAPI
from sharpit.fastapi import sink_ownership
from sharpit.fastapi.sink_ownership import owned, owner

SCOPE: ContextVar[Scope | None] = ContextVar("sink_ownership_scope", default=None)


def open_sink_path(path: str) -> None:
    """Helper in another test module that fires an open audit event from its frame."""
    from sharpit.engine.sensors import audit

    audit.hub._dispatch("open", (path, "r", 0))  # pyright: ignore[reportPrivateUsage]


class Recorder:
    """The probe: records whether the code that called it is owned by the request."""

    def __init__(self) -> None:
        self.seen: list[bool] = []
        self.owners: list[str | None] = []

    def __call__(self, scope: Scope | None = None) -> None:
        target = scope if scope is not None else SCOPE.get() or {}
        self.seen.append(owned(target))
        self.owners.append(owner(target))


class ScopeMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        token = SCOPE.set(scope)
        try:
            await self.app(scope, receive, send)
        finally:
            SCOPE.reset(token)


async def passthrough(request: Request, call_next: RequestResponseEndpoint) -> Response:
    return await call_next(request)


def serve(app: FastAPI, base_http_middleware: bool) -> TestClient:
    if base_http_middleware:
        app.add_middleware(BaseHTTPMiddleware, dispatch=passthrough)
    app.add_middleware(ScopeMiddleware)  # added last, so outermost
    return TestClient(app)


@dataclass
class Case:
    app: FastAPI
    probe: Recorder
    tmp_path: Path
    monkeypatch: pytest.MonkeyPatch


CASES: dict[str, Callable[[Case], str]] = {}


def case(name: str) -> Callable[[Callable[[Case], str]], Callable[[Case], str]]:
    def register(build: Callable[[Case], str]) -> Callable[[Case], str]:
        CASES[name] = build
        return build

    return register


# --- owned: the endpoint, its dependencies, and what they call or await directly


@case("sync")
def _sync(c: Case) -> str:
    @c.app.get("/case")
    def endpoint() -> None:
        c.probe()

    return "/case"


@case("async")
def _async(c: Case) -> str:
    @c.app.get("/case")
    async def endpoint() -> None:
        c.probe()

    return "/case"


@case("wraps_decorated")
def _wraps_decorated(c: Case) -> str:
    def traced(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs)

        return wrapper

    @c.app.get("/case")
    @traced
    async def endpoint() -> None:
        c.probe()

    return "/case"


@case("dependency")
def _dependency(c: Case) -> str:
    def dep() -> None:
        c.probe()

    @c.app.get("/case")
    def endpoint(_: None = Depends(dep)) -> None:
        return None

    return "/case"


@case("sub_dependency")
def _sub_dependency(c: Case) -> str:
    def inner() -> None:
        c.probe()

    def outer(_: None = Depends(inner)) -> None:
        return None

    @c.app.get("/case")
    def endpoint(_: None = Depends(outer)) -> None:
        return None

    return "/case"


@case("yield_dependency_exit")
def _yield_dependency_exit(c: Case) -> str:
    def dep() -> Iterator[None]:
        yield
        c.probe()

    @c.app.get("/case")
    def endpoint(_: None = Depends(dep)) -> None:
        return None

    return "/case"


@case("bound_method")
def _bound_method(c: Case) -> str:
    class Handlers:
        def endpoint(self) -> None:
            c.probe()

    c.app.add_api_route("/case", Handlers().endpoint, methods=["GET"])
    return "/case"


@case("partial")
def _partial(c: Case) -> str:
    def endpoint(label: str) -> None:
        c.probe()

    c.app.add_api_route("/case", functools.partial(endpoint, label="fixed"), methods=["GET"])
    return "/case"


@case("nested_await")
def _nested_await(c: Case) -> str:
    async def helper() -> None:
        c.probe()

    @c.app.get("/case")
    async def endpoint() -> None:
        await helper()

    return "/case"


@case("starlette_function")
def _starlette_function(c: Case) -> str:
    def endpoint(request: Request) -> Response:
        c.probe()
        return PlainTextResponse("ok")

    c.app.router.add_route("/case", endpoint)
    return "/case"


@case("starlette_class")
def _starlette_class(c: Case) -> str:
    class Endpoint(HTTPEndpoint):
        def get(self, request: Request) -> Response:
            c.probe()
            return PlainTextResponse("ok")

    c.app.router.add_route("/case", Endpoint)
    return "/case"


@case("class_dependency")
def _class_dependency(c: Case) -> str:
    class Pagination:
        def __init__(self, page: int = 1) -> None:
            c.probe()
            self.page = page

    @c.app.get("/case")
    def endpoint(pages: Annotated[Pagination, Depends(Pagination)]) -> None:
        return None

    return "/case"


@case("overridden_dependency")
def _overridden_dependency(c: Case) -> str:
    def dep() -> None:
        return None

    def fake() -> None:
        c.probe()

    @c.app.get("/case")
    def endpoint(_: None = Depends(dep)) -> None:
        return None

    c.app.dependency_overrides[dep] = fake
    return "/case"


def _engine(probe: Recorder) -> Any:
    """An aiosqlite engine whose ``before_cursor_execute`` listener probes: the statement runs in a child greenlet."""
    pytest.importorskip("aiosqlite")
    from sqlalchemy import event
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine("sqlite+aiosqlite://", poolclass=NullPool)
    event.listen(engine.sync_engine, "before_cursor_execute", lambda *_: probe())
    return engine


async def _select_one(engine: Any) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    async with AsyncSession(engine) as session:
        await session.execute(text("select 1"))


@case("sqlalchemy_async_session")
def _sqlalchemy_async_session(c: Case) -> str:
    engine = _engine(c.probe)

    @c.app.get("/case")
    async def endpoint() -> None:
        await _select_one(engine)

    return "/case"


@case("sqlalchemy_async_in_dependency")
def _sqlalchemy_async_in_dependency(c: Case) -> str:
    engine = _engine(c.probe)

    async def session() -> Any:
        await _select_one(engine)
        yield None

    @c.app.get("/case")
    async def endpoint(_: object = Depends(session)) -> None:
        return None

    return "/case"


# --- not owned: work the endpoint handed off, or that runs after it returned


@case("gather")
def _gather(c: Case) -> str:
    async def helper() -> None:
        c.probe()

    @c.app.get("/case")
    async def endpoint() -> None:
        await asyncio.gather(helper())

    return "/case"


@case("create_task")
def _create_task(c: Case) -> str:
    async def helper() -> None:
        c.probe()

    @c.app.get("/case")
    async def endpoint() -> None:
        await asyncio.create_task(helper())

    return "/case"


@case("to_thread")
def _to_thread(c: Case) -> str:
    def helper() -> None:
        c.probe()

    @c.app.get("/case")
    async def endpoint() -> None:
        await asyncio.to_thread(helper)

    return "/case"


@case("anyio_thread")
def _anyio_thread(c: Case) -> str:
    def helper() -> None:
        c.probe()

    @c.app.get("/case")
    async def endpoint() -> None:
        await anyio.to_thread.run_sync(helper)

    return "/case"


@case("raw_thread")
def _raw_thread(c: Case) -> str:
    def helper(scope: Scope) -> None:
        c.probe(scope)  # a raw thread copies no context: the scope is passed explicitly

    @c.app.get("/case")
    def endpoint() -> None:
        thread = threading.Thread(target=helper, args=(SCOPE.get(),))
        thread.start()
        thread.join()

    return "/case"


@case("background_task")
def _background_task(c: Case) -> str:
    def helper() -> None:
        c.probe()

    @c.app.get("/case")
    def endpoint(tasks: BackgroundTasks) -> None:
        tasks.add_task(helper)

    return "/case"


@case("stream_body")
def _stream_body(c: Case) -> str:
    async def body() -> Any:
        c.probe()
        yield b"x"

    @c.app.get("/case")
    async def endpoint() -> Response:
        return StreamingResponse(body())

    return "/case"


@case("file_response")
def _file_response(c: Case) -> str:
    target = c.tmp_path / "report.txt"
    target.write_text("report")
    real_open_file = anyio.open_file

    async def open_file(file: Any, *args: Any, **kwargs: Any) -> Any:
        if os.fspath(file) == os.fspath(target):
            await anyio.to_thread.run_sync(c.probe)  # where Starlette's own open runs: a worker thread
        return await real_open_file(file, *args, **kwargs)

    c.monkeypatch.setattr(anyio, "open_file", open_file)

    @c.app.get("/case")
    async def endpoint() -> Response:
        return FileResponse(target)

    return "/case"


@case("raw_asgi_mount_background")
def _raw_asgi_mount_background(c: Case) -> str:
    class Raw:
        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            await asyncio.create_task(self.work())
            await PlainTextResponse("ok")(scope, receive, send)

        async def work(self) -> None:
            c.probe()

    c.app.mount("/raw", Raw())
    return "/raw/case"


@case("sqlalchemy_async_in_create_task")
def _sqlalchemy_async_in_create_task(c: Case) -> str:
    engine = _engine(c.probe)

    @c.app.get("/case")
    async def endpoint() -> None:
        await asyncio.create_task(_select_one(engine))

    return "/case"


OWN = [
    "sync",
    "async",
    "wraps_decorated",
    "dependency",
    "sub_dependency",
    "yield_dependency_exit",
    "bound_method",
    "partial",
    "nested_await",
    "starlette_function",
    "starlette_class",
    "class_dependency",
    "overridden_dependency",
    "sqlalchemy_async_session",
    "sqlalchemy_async_in_dependency",
]
NOT_OWN = [
    "gather",
    "create_task",
    "to_thread",
    "anyio_thread",
    "raw_thread",
    "background_task",
    "stream_body",
    "file_response",
    "raw_asgi_mount_background",
    "sqlalchemy_async_in_create_task",
]


def _params(names: list[str]) -> list[Any]:
    return [pytest.param(n, marks=pytest.mark.needs_sqlalchemy) if n.startswith("sqlalchemy") else n for n in names]


def run_case(name: str, base_http_middleware: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    probe = Recorder()
    app = FastAPI()
    path = CASES[name](Case(app, probe, tmp_path, monkeypatch))
    response = serve(app, base_http_middleware).get(path)
    assert response.status_code == 200
    return probe.seen


@pytest.mark.parametrize("base_http_middleware", [False, True])
@pytest.mark.parametrize("case", _params(OWN + NOT_OWN))
def test_only_the_endpoints_own_stack_is_owned(
    case: str, base_http_middleware: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = run_case(case, base_http_middleware, tmp_path, monkeypatch)
    assert seen != []
    assert set(seen) == {case in OWN}


def test_an_empty_scope_is_not_owned() -> None:
    assert owned({}) is False


class Hostile:
    """A route no attribute of which may be read."""

    def __getattribute__(self, name: str) -> Any:
        raise RuntimeError("no attribute of this route may be read")


def test_a_route_whose_every_attribute_raises_is_not_owned() -> None:
    # the endpoint named is this very function, on the stack: only the failing route keeps the answer False
    assert owned({"endpoint": test_a_route_whose_every_attribute_raises_is_not_owned, "route": Hostile()}) is False


class CountingPartial(functools.partial[None]):
    """A partial that counts how often the ownership module unwraps it: once per code set it builds."""

    @property
    def func(self) -> Callable[..., None]:  # type: ignore[override]
        if sys._getframe(1).f_globals.get("__name__") == sink_ownership.__name__:
            self.__dict__["reads"] = self.__dict__.get("reads", 0) + 1
        return functools.partial.func.__get__(self)  # type: ignore[attr-defined]

    @property
    def reads(self) -> int:
        return self.__dict__.get("reads", 0)


def test_the_code_set_is_built_once_per_route_although_routes_are_unhashable() -> None:
    # scenario row 3: Starlette routes define __eq__ without __hash__, so the cache keys by identity
    probe = Recorder()

    def listing(label: str) -> None:
        probe()

    endpoint = CountingPartial(listing, label="fixed")
    app = FastAPI()
    app.add_api_route("/case", endpoint, methods=["GET"])
    route = next(r for r in app.routes if getattr(r, "path", None) == "/case")
    assert type(route).__hash__ is None
    client = serve(app, False)
    reads: list[int] = []
    for _ in range(2):
        assert client.get("/case").status_code == 200
        reads.append(endpoint.reads)
    assert probe.seen == [True, True]
    assert reads[0] > 0
    assert reads[1] == reads[0]


def test_a_class_endpoint_owns_each_method_after_another_was_cached() -> None:
    # scenario row 4: the GET handler's set is cached first; the POST handler is still owned
    probe = Recorder()

    class Report(HTTPEndpoint):
        def get(self, request: Request) -> Response:
            probe()
            return PlainTextResponse("got")

        async def post(self, request: Request) -> Response:
            probe()
            return PlainTextResponse("posted")

    app = FastAPI()
    app.router.add_route("/report", Report)
    client = serve(app, False)
    assert client.get("/report").status_code == 200
    assert client.post("/report").status_code == 200
    assert probe.seen == [True, True]


def test_eager_task_first_step_is_owned_as_documented() -> None:
    # D1 limitation: under asyncio.eager_task_factory a child task's first step runs inside create_task, with the
    # endpoint's frames below it, so it counts as owned; a lazy task is not (the create_task case above)
    probe = Recorder()

    async def first_step() -> None:
        probe()

    app = FastAPI()

    @app.get("/case")
    async def endpoint() -> None:
        loop = asyncio.get_running_loop()
        previous = loop.get_task_factory()
        loop.set_task_factory(asyncio.eager_task_factory)
        try:
            await asyncio.create_task(first_step())
        finally:
            loop.set_task_factory(previous)

    assert serve(app, False).get("/case").status_code == 200
    assert probe.seen == [True]


def test_a_plain_starlette_route_caches_by_endpoint() -> None:
    # D1: FastAPI leaves scope["route"] unset for a plain Starlette Route on its router; the endpoint keys the cache
    probe = Recorder()
    fallback: list[bool] = []

    def report(request: Request, label: str) -> Response:
        probe()
        fallback.append(owned({"route": None, "endpoint": request.scope["endpoint"]}))
        return PlainTextResponse("ok")

    endpoint = CountingPartial(report, label="fixed")
    app = FastAPI()
    app.router.add_route("/report", endpoint)
    client = serve(app, False)
    reads: list[int] = []
    for _ in range(2):
        assert client.get("/report").status_code == 200
        reads.append(endpoint.reads)
    assert probe.seen == [True, True]
    assert fallback == [True, True]
    assert reads[0] > 0
    assert reads[1] == reads[0]


def test_two_concurrent_requests_never_match_each_others_values() -> None:
    import httpx

    from sharpit.engine.capture.correlation import REQUEST, RequestInfo, new_request_id
    from sharpit.engine.sensors.sinks.values import RequestValues

    values = RequestValues()
    barrier = asyncio.Barrier(2)
    results: dict[str, tuple[bool, tuple[str, ...], tuple[str, ...]]] = {}

    class RequestMiddleware:
        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            info = RequestInfo(new_request_id(), "ctx", "GET", scope["path"], None, 0, None, scope=scope)
            token = REQUEST.set(info)
            try:
                await self.app(scope, receive, send)
            finally:
                REQUEST.reset(token)
                info.finished_ns = 1
                values.end(info.id)

    async def check(own_path: str, other_path: str) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
        await barrier.wait()
        info = REQUEST.get()
        assert info is not None
        assert info.scope is not None
        result = (
            owned(info.scope),
            values.match(info, own_path, "file").names,
            values.match(info, other_path, "file").names,
        )
        await barrier.wait()
        return result

    app = FastAPI()
    app.add_middleware(RequestMiddleware)

    @app.get("/first")
    async def first() -> None:
        results["first"] = await check("/srv/alpha-one.txt", "/srv/bravo-two.txt")

    @app.get("/second")
    async def second() -> None:
        results["second"] = await check("/srv/bravo-two.txt", "/srv/alpha-one.txt")

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            first_res, second_res = await asyncio.gather(
                client.get("/first?first=alpha-one"),
                client.get("/second?second=bravo-two"),
            )
            assert first_res.status_code == 200
            assert second_res.status_code == 200

    asyncio.run(run())
    assert results["first"] == (True, ("first",), ())
    assert results["second"] == (True, ("second",), ())
    assert values.held() == 0


def test_a_dependency_override_set_after_the_first_request_is_owned() -> None:
    # scenario: plan-1 row 16: the cached code set follows app.dependency_overrides
    probe = Recorder()

    def dep() -> None:
        probe()

    def fake() -> None:
        probe()

    app = FastAPI()

    @app.get("/case")
    def endpoint(_: None = Depends(dep)) -> None:
        return None

    client = serve(app, False)
    assert client.get("/case").status_code == 200
    app.dependency_overrides[dep] = fake
    assert client.get("/case").status_code == 200
    app.dependency_overrides.clear()
    assert client.get("/case").status_code == 200
    assert probe.seen == [True, True, True]


@pytest.mark.parametrize("case", _params(OWN + NOT_OWN))
def test_owner_and_owned_agree_on_every_case(case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    probe = Recorder()
    app = FastAPI()
    path = CASES[case](Case(app, probe, tmp_path, monkeypatch))
    response = serve(app, False).get(path)
    assert response.status_code == 200
    assert probe.owners != []
    assert [site is not None for site in probe.owners] == probe.seen
    assert set(probe.seen) == {case in OWN}
    if case in OWN:
        assert all(isinstance(site, str) for site in probe.owners)
        assert all(":" in (site or "") for site in probe.owners)
