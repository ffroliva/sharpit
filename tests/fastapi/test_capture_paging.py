from fastapi.routing import APIRoute

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sharpit import install
from sharpit.engine.capture.correlation import PagingContext, REQUEST, paging_of


def _route() -> APIRoute:
    app = FastAPI()

    @app.get("/items")
    def items(skip: int = 0, limit: int = 10) -> list[int]:
        return []

    return next(route for route in app.routes if isinstance(route, APIRoute))


def test_paging_context_uses_bound_limit() -> None:
    result = paging_of({"route": _route(), "query_string": b"skip=3&limit=7"})
    assert result is not None
    assert result.page_size == 7
    assert result.route == "/items"


def test_paging_context_uses_bound_page_size() -> None:
    app = FastAPI()

    @app.get("/items")
    def items(page_size: int = 10) -> list[int]:
        return []

    route = next(item for item in app.routes if isinstance(item, APIRoute))
    result = paging_of({"route": route, "query_string": b"page_size=7"})

    assert result is not None
    assert result.page_size == 7


def test_paging_context_does_not_guess_from_offset_or_page() -> None:
    route = FastAPI()

    @route.get("/items")
    def items(offset: int = 0, page: int = 1) -> list[int]:
        return []

    apiroute = next(item for item in route.routes if isinstance(item, APIRoute))
    result = paging_of({"route": apiroute, "query_string": b"offset=4&page=2"})
    assert result is not None
    assert result.page_size is None


def test_invalid_bound_page_sizes_are_ignored() -> None:
    for query in (b"limit=0", b"limit=-1", b"limit=invalid", b"limit=2&limit=3"):
        result = paging_of({"route": _route(), "query_string": query})
        assert result is not None
        assert result.page_size is None


def test_paging_route_without_bound_page_size_does_not_guess() -> None:
    app = FastAPI()

    @app.get("/items")
    def items(skip: int = 0, offset: int = 0, page: int = 1) -> list[int]:
        return []

    route = next(item for item in app.routes if isinstance(item, APIRoute))
    result = paging_of({"route": route, "query_string": b"skip=30&offset=5&page=4"})

    assert result is not None
    assert result.page_size is None


def test_page_size_binding_validation_is_conservative() -> None:
    huge = b"limit=" + b"9" * 5000
    for query in (b"limit=0", b"limit=-1", b"limit=invalid", b"limit=1&limit=2", huge):
        result = paging_of({"route": _route(), "query_string": query})
        assert result is not None
        assert result.page_size is None


def test_paging_context_reset_after_exception() -> None:
    app = FastAPI()
    observed = []

    @app.get("/raise")
    def fail(limit: int = 5) -> None:
        raise RuntimeError("request failed")

    handle = install(app, enabled="ON", show_banner=False)

    async def outer(scope, receive, send):
        observed.append(REQUEST.get())
        try:
            await app(scope, receive, send)
        finally:
            observed.append(REQUEST.get())

    try:
        response = TestClient(outer, raise_server_exceptions=False).get("/raise?limit=5")
    finally:
        handle.uninstall_capture()

    assert response.status_code == 500
    assert observed == [None, None]


def test_paging_computed_lazily_after_route_match() -> None:
    app = FastAPI()
    observed: list[PagingContext | None] = []

    @app.middleware("http")
    async def route_not_matched_at_request_start(request, call_next):
        observed.append(paging_of(request.scope))
        response = await call_next(request)
        observed.append(paging_of(request.scope))
        return response

    @app.get("/items")
    def items(limit: int = 5) -> list[int]:
        return []

    handle = install(app, enabled="ON", show_banner=False)
    try:
        response = TestClient(app).get("/items?limit=5")
    finally:
        handle.uninstall_capture()

    assert response.status_code == 200
    assert observed[0] is None
    assert observed[1] is not None
    context = observed[1]
    assert context is not None
    assert context.page_size == 5
