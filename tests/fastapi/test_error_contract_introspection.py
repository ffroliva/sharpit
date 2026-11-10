"""FastAPI declarations collected for the REST API error-contract panel."""

import functools

from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.restapi.error_contract import error_contract_report
from sharpit.fastapi.introspector import FastApiIntrospector


def test_error_contract_keeps_app_handler_for_framework_exception() -> None:
    app = FastAPI()

    @app.exception_handler(HTTPException)
    async def host_http_error(_request: object, _exc: HTTPException) -> JSONResponse:
        return JSONResponse({"detail": "hidden-value"}, status_code=418)

    model = FastApiIntrospector(app).api_model()
    handlers = getattr(model, "error_handlers", ())
    assert any(handler.handler.endswith("host_http_error") for handler in handlers)


def test_error_contract_scopes_mounted_subapp_handlers() -> None:
    subapp = FastAPI()

    @subapp.exception_handler(ValueError)
    async def subapp_error(_request: object, _exc: ValueError) -> JSONResponse:
        return JSONResponse({"detail": "hidden-value"}, status_code=400)

    app = FastAPI()
    app.mount("/mounted", subapp)
    model = FastApiIntrospector(app).api_model()
    handlers = getattr(model, "error_handlers", ())
    assert any(handler.handler.endswith("subapp_error") for handler in handlers)
    mounted = next(handler for handler in handlers if handler.handler.endswith("subapp_error"))
    assert mounted.scope == "SCOPED"
    assert mounted.scope_target == "/mounted"


def test_error_contract_handles_integer_exception_handler_keys() -> None:
    app = FastAPI()

    async def status_error(_request: object, _exc: Exception) -> JSONResponse:
        return JSONResponse({}, status_code=404)

    app.exception_handlers[404] = status_error
    model = FastApiIntrospector(app).api_model()
    handlers = getattr(model, "error_handlers", ())
    assert any(handler.key_status == 404 and handler.handler.endswith("status_error") for handler in handlers)


def test_error_contract_handles_partial_and_callable_handlers() -> None:
    app = FastAPI()

    async def partial_handler(_request: object, _exc: Exception) -> JSONResponse:
        return JSONResponse({})

    class CallableHandler:
        async def __call__(self, _request: object, _exc: Exception) -> JSONResponse:
            return JSONResponse({})

    app.exception_handlers[ValueError] = functools.partial(partial_handler)
    app.exception_handlers[LookupError] = CallableHandler()
    handlers = getattr(FastApiIntrospector(app).api_model(), "error_handlers", ())
    assert any(handler.handler.endswith("partial_handler") for handler in handlers)
    assert any(handler.handler.endswith("CallableHandler") for handler in handlers)


def test_error_contract_golden_shape_23(tmp_path) -> None:
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, config_scan=False, state_dir=str(tmp_path / "state"))
    try:
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            response = client.get("/sharpit/api/rest-api/error-contract")
            assert response.status_code == 200
            report = response.json()
            assert set(report) == {
                "available",
                "unavailableReason",
                "total",
                "handlerCount",
                "componentCount",
                "exceptionTypeCount",
                "truncated",
                "maxEntries",
                "entries",
                "page",
            }
            assert set(report["page"]) == {"total", "matched", "offset", "limit", "returned", "hasMore"}
            invalid = client.get("/sharpit/api/rest-api/error-contract", params={"offset": "bad"})
            assert invalid.status_code == 400
            assert invalid.json() == {"error": "Invalid 'offset' parameter"}
    finally:
        handle.uninstall_capture()


def test_error_contract_excludes_framework_and_sharpit_handlers() -> None:
    app = FastAPI()
    model = FastApiIntrospector(app, exclude_mount="/sharpit").api_model()
    report = error_contract_report(model, None, None, 0, None)
    assert report["available"] is True
    assert report["entries"] == []


def test_rest_api_error_contract_has_no_write_routes(tmp_path) -> None:
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, config_scan=False, state_dir=str(tmp_path / "state"))
    try:
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            response = client.post("/sharpit/api/rest-api/error-contract")
            assert response.status_code == 405
    finally:
        handle.uninstall_capture()
