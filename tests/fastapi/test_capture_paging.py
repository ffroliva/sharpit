from fastapi.routing import APIRoute

from fastapi import FastAPI
from sharpit.engine.capture.correlation import paging_of


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
