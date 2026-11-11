"""FastAPI declarations collected for the REST API error-contract panel."""

import functools
import inspect
import json
from collections.abc import Mapping
from pathlib import Path

from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.restapi.error_contract import error_contract_report
from sharpit.fastapi.introspector import FastApiIntrospector


async def _source_index_handler(_request: object, _exc: ValueError) -> JSONResponse:
    return JSONResponse({"detail": "x"}, status_code=400)


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
    row = next(handler for handler in handlers if handler.key_status == 404)
    assert row.handler.endswith("status_error")
    assert row.scope == "SCOPED"
    assert row.scope_target == "status=404"


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


def test_error_contract_rejects_host_mapping_without_iterating_it() -> None:
    called = False

    class HostMapping(Mapping):
        def __getitem__(self, key):
            raise AssertionError("must not index host mapping")

        def __iter__(self):
            raise AssertionError("must not iterate host mapping")

        def __len__(self):
            return 1

        def items(self):
            nonlocal called
            called = True
            raise AssertionError("must not call host items")

    app = FastAPI()
    app.exception_handlers = HostMapping()
    handlers = FastApiIntrospector(app).api_model().error_handlers
    assert handlers == ()
    assert called is False


def test_error_contract_one_bad_handler_does_not_hide_its_siblings() -> None:
    app = FastAPI()

    async def opaque_handler(_request: object, _exc: Exception) -> JSONResponse:
        return JSONResponse({})

    async def valid_handler(_request: object, _exc: Exception) -> JSONResponse:
        return JSONResponse({})

    opaque_handler.__wrapped__ = opaque_handler
    app.exception_handlers[ValueError] = opaque_handler
    app.exception_handlers[LookupError] = valid_handler
    model = FastApiIntrospector(app).api_model()
    assert any(handler.key_type == "LookupError" for handler in model.error_handlers)
    assert any("could not be inspected" in note for note in model.limitations)


def test_error_contract_exception_name_is_dotted() -> None:
    app = FastAPI()

    class CustomHostError(Exception):
        pass

    app.exception_handlers[ValueError] = lambda _request, _exc: None
    app.exception_handlers[CustomHostError] = lambda _request, _exc: None
    handlers = FastApiIntrospector(app).api_model().error_handlers
    assert any(handler.key_type == "ValueError" for handler in handlers)
    assert any(handler.key_type is not None and handler.key_type.endswith(".CustomHostError") for handler in handlers)


def test_error_contract_installed_app_still_reports_exception_handlers(tmp_path) -> None:
    app = FastAPI()

    async def custom_handler(_request: object, _exc: ValueError) -> JSONResponse:
        return JSONResponse({"error": "test"}, status_code=400)

    app.exception_handlers[ValueError] = custom_handler
    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        state_dir=str(tmp_path / "state"),
    )
    try:
        model = FastApiIntrospector(app).api_model()
        assert any(h.endswith("custom_handler") for h in model.exception_handlers)
    finally:
        handle.uninstall_capture()


def test_error_contract_unwrapping_never_accesses_host_attributes() -> None:
    ran: list[tuple[str, str]] = []

    class Host:
        def __getattr__(self, name: str) -> None:
            ran.append(("getattr", name))
            raise AttributeError(name)

        @property
        def __module__(self) -> str:
            ran.append(("prop", "__module__"))
            return "host_module"

    async def host_handler(_request: object, _exc: Exception) -> JSONResponse:
        return JSONResponse({})

    host_handler.__wrapped__ = Host()  # type: ignore[attr-defined]
    app = FastAPI()
    app.exception_handlers[ValueError] = host_handler
    model = FastApiIntrospector(app).api_model()
    assert ran == []
    assert any(h.handler.endswith("host_handler") for h in model.error_handlers)


def test_error_contract_int_key_in_subapps_retains_mount_path() -> None:
    subapp1, subapp2 = FastAPI(), FastAPI()

    async def not_found(_request: object, _exc: Exception) -> JSONResponse:
        return JSONResponse({}, status_code=404)

    subapp1.exception_handlers[404] = not_found
    subapp2.exception_handlers[404] = not_found
    app = FastAPI()
    app.mount("/a", subapp1)
    app.mount("/b", subapp2)
    handlers = FastApiIntrospector(app).api_model().error_handlers
    mounts = [h.scope_target for h in handlers if h.key_status == 404]
    assert mounts == ["/a", "/b"]


def test_error_contract_custom_metaclass_exception_records_limitation() -> None:
    class Meta(type):
        pass

    class OddError(Exception, metaclass=Meta):
        pass

    app = FastAPI()
    app.exception_handlers[OddError] = lambda _request, _exc: None
    model = FastApiIntrospector(app).api_model()
    assert any(h.key_type is None and h.key_status is None for h in model.error_handlers)
    assert any("could not be inspected" in limitation for limitation in model.limitations)


def test_error_contract_same_subapp_is_reported_at_each_mount() -> None:
    subapp = FastAPI()
    subapp.exception_handlers[ValueError] = lambda _request, _exc: None
    app = FastAPI()
    app.mount("/a", subapp)
    app.mount("/b", subapp)
    mounts = [h.scope_target for h in FastApiIntrospector(app).api_model().error_handlers if h.key_type == "ValueError"]
    assert mounts == ["/a", "/b"]


def test_error_contract_walks_router_mount_and_notes_host_routes() -> None:
    from starlette.routing import Host, Mount, Router

    router = Router()
    subapp = FastAPI()
    subapp.exception_handlers[ValueError] = lambda _request, _exc: None
    router.routes.append(Mount("/nested", app=subapp))
    app = FastAPI()
    app.router.routes.append(Mount("/router", app=router))
    app.router.routes.append(Host("{sub}.example.org", app=Router()))
    model = FastApiIntrospector(app).api_model()
    assert any(h.key_type == "ValueError" and h.scope_target == "/router/nested" for h in model.error_handlers)
    assert any("Host routes" in limitation for limitation in model.limitations)


def test_installed_callable_instance_and_partial_handlers_are_reported(tmp_path) -> None:
    app = FastAPI()

    async def base(_request, _exc, extra):
        return JSONResponse({})

    class Callable:
        async def __call__(self, _request, _exc):
            return JSONResponse({})

    app.exception_handlers[ValueError] = functools.partial(base, extra="x")
    app.exception_handlers[LookupError] = Callable()
    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        state_dir=str(tmp_path / "state"),
    )
    try:
        handlers = FastApiIntrospector(app, exclude_mount="/sharpit").api_model().error_handlers
        assert any(h.key_type == "ValueError" for h in handlers)
        assert any(h.key_type == "LookupError" for h in handlers)
    finally:
        handle.uninstall_capture()


def test_error_contract_golden_shape_23(tmp_path) -> None:
    app = FastAPI()

    @app.exception_handler(ValueError)
    async def golden_host_handler(_request: object, _exc: ValueError) -> JSONResponse:
        return JSONResponse({}, 400)

    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        state_dir=str(tmp_path / "state"),
    )
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
            golden = json.loads(Path("tests/fixtures/bootui/2.3.0/rest-api/error-contract.captured.json").read_text())
            assert report["entries"]
            assert set(report["entries"][0]) == set(golden["entries"][0])
            invalid = client.get("/sharpit/api/rest-api/error-contract", params={"offset": "bad"})
            assert invalid.status_code == 400
            assert invalid.json() == {"error": "Invalid 'offset' parameter"}
    finally:
        handle.uninstall_capture()


def test_error_contract_excludes_framework_and_sharpit_handlers() -> None:
    # ported: SpringErrorContractProviderTests.excludesBootUisOwnComponentsFromTheApplicationsContract
    app = FastAPI()
    model = FastApiIntrospector(app, exclude_mount="/sharpit").api_model()
    report = error_contract_report(model, None, None, 0, None)
    assert report["available"] is True
    assert report["entries"] == []


def test_error_contract_still_reports_application_handler_for_framework_exception() -> None:
    # ported: ErrorContractServiceTests.stillReportsAnApplicationHandlerForAFrameworkException
    app = FastAPI()

    @app.exception_handler(HTTPException)
    async def application_http_error(_request: object, _exc: HTTPException) -> JSONResponse:
        return JSONResponse({}, status_code=418)

    handlers = FastApiIntrospector(app).api_model().error_handlers
    assert any(handler.key_type == "starlette.exceptions.HTTPException" for handler in handlers)
    assert any(handler.handler.endswith("application_http_error") for handler in handlers)


def test_error_contract_route_derives_body_from_source_index_without_inspect(tmp_path, monkeypatch) -> None:
    app = FastAPI()
    app.exception_handlers[ValueError] = _source_index_handler
    monkeypatch.setattr(inspect, "getsource", lambda *_args: (_ for _ in ()).throw(AssertionError("inspect source")))
    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        app_package=__name__,
        state_dir=str(tmp_path / "state"),
    )
    try:
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            entries = client.get("/sharpit/api/rest-api/error-contract").json()["entries"]
        assert any(item["exceptionType"] == "ValueError" for item in entries)
        entry = next(item for item in entries if item["exceptionType"] == "ValueError")
        assert entry["bodyCategory"] == "CUSTOM_OBJECT"
    finally:
        handle.uninstall_capture()


def test_error_contract_route_keeps_partial_handler_unresolved(tmp_path) -> None:
    app = FastAPI()
    app.exception_handlers[ValueError] = functools.partial(_source_index_handler)
    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        app_package=__name__,
        state_dir=str(tmp_path / "state"),
    )
    try:
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            entries = client.get("/sharpit/api/rest-api/error-contract").json()["entries"]
        assert any(item["exceptionType"] == "ValueError" for item in entries)
        entry = next(item for item in entries if item["exceptionType"] == "ValueError")
        assert entry["bodyCategory"] == "UNRESOLVED"
    finally:
        handle.uninstall_capture()


def test_rest_api_error_contract_has_no_write_routes(tmp_path) -> None:
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, config_scan=False, state_dir=str(tmp_path / "state"))
    try:
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            response = client.post("/sharpit/api/rest-api/error-contract")
            assert response.status_code == 405
    finally:
        handle.uninstall_capture()


def test_error_contract_reports_the_host_function_under_capture(tmp_path) -> None:
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, config_scan=False, state_dir=str(tmp_path / "state"))
    try:

        @app.exception_handler(ValueError)
        async def late_host_handler(_request: object, _exc: ValueError) -> JSONResponse:
            return JSONResponse({"detail": "x"}, status_code=400)

        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            entries = client.get("/sharpit/api/rest-api/error-contract").json()["entries"]
            handlers = {f"{entry['component']}:{entry['method']}" for entry in entries}
            assert any(h.endswith("late_host_handler") for h in handlers)
            assert not any("sync_wrapper" in h or "async_wrapper" in h for h in handlers)
    finally:
        handle.uninstall_capture()


_PANEL_GETS = ("/sharpit/api/rest-api", "/sharpit/api/rest-api/error-contract")


def _armed_gets(app: FastAPI, tmp_path: Path, armed: list[bool]) -> list[int]:
    handle = install(app, enabled="ON", show_banner=False, config_scan=False, state_dir=str(tmp_path / "state"))
    try:
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            armed[0] = True
            statuses = [client.get(path).status_code for path in _PANEL_GETS]
            armed[0] = False
    finally:
        handle.uninstall_capture()
    return statuses


def test_panel_gets_never_run_a_callable_handler_class_code(tmp_path) -> None:
    armed = [False]
    ran: list[str] = []

    class RecordingHandler:
        def __getattribute__(self, name: str) -> object:
            if armed[0]:
                ran.append(name)
            return object.__getattribute__(self, name)

        @property
        def __module__(self) -> str:  # pyright: ignore[reportIncompatibleVariableOverride]
            if armed[0]:
                ran.append("__module__ property")
            return "host_module"

        async def __call__(self, _request: object, _exc: Exception) -> JSONResponse:
            return JSONResponse({})

    app = FastAPI()
    app.exception_handlers[KeyError] = RecordingHandler()
    assert _armed_gets(app, tmp_path, armed) == [200, 200]
    assert ran == []


def test_error_contract_get_never_truth_tests_a_mounted_app(tmp_path) -> None:
    armed = [False]
    ran: list[str] = []

    class TruthyApp(FastAPI):
        def __len__(self) -> int:
            if armed[0]:
                ran.append("__len__")
            return 0

        def __bool__(self) -> bool:
            if armed[0]:
                ran.append("__bool__")
            return False

    sub = TruthyApp()
    sub.exception_handlers[KeyError] = _source_index_handler
    app = FastAPI()
    app.mount("/a", sub)
    assert _armed_gets(app, tmp_path, armed) == [200, 200]
    assert ran == []
