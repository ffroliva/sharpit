"""FastAPI binding diagnostics; source parity is cited at each ported behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field, create_model
from starlette.requests import Request
from starlette.responses import JSONResponse

from fastapi import FastAPI
from sharpit import install
from sharpit.fastapi.binding_diagnostics import validation_details


class Profile(BaseModel):
    email: str


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: int
    profile: Profile = Field(alias="person")


def _route() -> object:
    app = FastAPI()

    @app.post("/payload")
    def payload(value: Payload) -> None:  # pyright: ignore[reportUnusedFunction]
        return None

    return app.routes[-1]


def test_binding_corpus_r1_through_r12_is_safe_and_bounded() -> None:
    # ported: SpringBindingDiagnosticsExtractorTests.extractsJackson3InvalidFormatAndUnrecognizedPropertyAndNeverLeaksValuesInMaskedOrMetadataOnly  # noqa: E501
    # ported: ExceptionsServiceTests.capsBindingDiagnosticsPerOccurrenceAtTenAndMarksTruncation
    route = _route()
    rows = [
        {"type": "int_parsing", "loc": ("body", "display_name"), "input": "S3NT1NEL"},
        {
            "type": "value_error",
            "loc": ("body", "person", "email"),
            "msg": "invalid ordinary-secret-91",
            "ctx": {"value": ["ordinary-secret-91"]},
        },
        {"type": "dict_type", "loc": ("body", "S3NT1NEL")},
        {"type": "int_parsing", "loc": ("body", "records", 0, "S3NT1NEL")},
        {
            "type": "extra_forbidden",
            "loc": ("body", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjb3JwdXMifQ.c2lnbmF0dXJlLWJ5dGVz"),
        },
        {"type": "ordinary-secret-91", "loc": ("body", "display_name")},
        {
            "type": "int_parsing",
            "loc": ("body", "records", 2, "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjb3JwdXMifQ.c2lnbmF0dXJlLWJ5dGVz"),
        },
        {"type": "json_invalid", "loc": ("body", 9)},
        {"type": "int_parsing", "loc": ("body", "person", "email")},
        {
            "type": "extra_forbidden",
            "loc": ("body", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjb3JwdXMifQ.c2lnbmF0dXJlLWJ5dGVz"),
        },
        {"type": "int_parsing", "loc": ("body", "display_name")},
        *[
            {"type": kind, "loc": ("body", "long_unknown")}
            for kind in (
                "string_type",
                "bool_type",
                "float_type",
                "int_type",
                "list_type",
                "dict_type",
                "set_type",
                "tuple_type",
                "bytes_type",
                "date_type",
                "time_type",
                "datetime_type",
            )
        ],
    ]

    class HostileValidationError(RequestValidationError):
        def __init__(self, errors: list[dict[str, Any]]) -> None:
            Exception.__init__(self)
            self._errors = errors

        def errors(self) -> list[dict[str, Any]]:
            return self._errors

        @property
        def body(self) -> Any:
            raise AssertionError("body must not be read")

        def __str__(self) -> str:
            raise AssertionError("validation exception must not be stringified")

    for exposure in ("MASKED", "METADATA_ONLY", "FULL"):
        exc = HostileValidationError(rows)
        message, diagnostics, truncated = validation_details(exc, route, exposure == "FULL")
        assert message == "23 validation errors"
        assert len(diagnostics) == 10
        assert truncated is True
        assert all(row["targetType"] == "Payload" for row in diagnostics)
        if exposure != "FULL":
            assert all("S3NT1NEL" not in str(row["fieldPath"]) for row in diagnostics)
        assert all("api_token" not in str(row["fieldPath"]) for row in diagnostics)
        assert all("ordinary-secret-91" not in str(row["fieldPath"]) for row in diagnostics)
        assert any(row["fieldPath"] == "(body)" for row in diagnostics)

    # R1–R11 are checked independently so the R12 cap cannot hide an earlier row.
    corpus = [
        (
            {"type": "int_parsing", "loc": ("body", "display_name"), "input": "S3NT1NEL"},
            "display_name",
            "display_name",
            "display_name",
        ),
        (
            {
                "type": "value_error",
                "loc": ("body", "person", "email"),
                "msg": "ordinary-secret-91",
                "ctx": {"value": ["ordinary-secret-91"]},
            },
            "person.email",
            "person.email",
            "person.email",
        ),
        ({"type": "dict_type", "loc": ("body", "S3NT1NEL")}, "[*]", "[*]", "['S3NT1NEL']"),
        (
            {"type": "int_parsing", "loc": ("body", "records", 0, "S3NT1NEL", "[key]")},
            "[*][*][*][*]",
            "[*][*][*][*]",
            "['records'][*]['S3NT1NEL'][*]",
        ),
        (
            {
                "type": "extra_forbidden",
                "loc": ("body", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjb3JwdXMifQ.c2lnbmF0dXJlLWJ5dGVz"),
            },
            "(unrecognized property)",
            "(unrecognized property)",
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjb3JwdXMifQ.c2lnbmF0dXJlLWJ5dGVz",
        ),
        (
            {"type": "ordinary-secret-91", "loc": ("body", "display_name")},
            "display_name",
            "display_name",
            "display_name",
        ),
        (
            {
                "type": "int_parsing",
                "loc": ("body", "records", 2, "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjb3JwdXMifQ.c2lnbmF0dXJlLWJ5dGVz"),
            },
            "[*][*][*]",
            "[*][*][*]",
            "['records'][*]['eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjb3JwdXMifQ.c2lnbmF0dXJlLWJ5dGVz']",
        ),
        ({"type": "json_invalid", "loc": ("body", 9)}, "(body)", "(body)", "(body)"),
        ({"type": "int_parsing", "loc": ("body", "person", "email")}, "person.email", "person.email", "person.email"),
        ({"type": "int_parsing", "loc": ("body", "person", "email")}, "person.email", "person.email", "person.email"),
        ({"type": "int_parsing", "loc": ("body", "display_name")}, "display_name", "display_name", "display_name"),
    ]
    for row, masked_path, metadata_path, full_path in corpus:
        for mode, expected_path in (("MASKED", masked_path), ("METADATA_ONLY", metadata_path), ("FULL", full_path)):
            _, result, _ = validation_details(RequestValidationError([row]), route, mode == "FULL")
            assert result[0]["fieldPath"] == expected_path


def test_binding_path_allowlist_alias_unknown_fallback_and_deduplication() -> None:
    # ported: ExceptionsServiceTests.extractsPerOccurrenceBindingDiagnosticsAndRedactsMapKeysAndUnrecognizedPropertiesExceptInFull  # noqa: E501
    route = _route()
    errors = [
        {"type": "int_parsing", "loc": ("body", "person", "email")},
        {"type": "int_parsing", "loc": ("body", "person", "email")},
        {"type": "extra_forbidden", "loc": ("body", "strange_key")},
        {"type": "bad_custom_reason", "loc": None},
    ]
    _, masked, truncated = validation_details(RequestValidationError(errors), route, False)
    assert truncated is False
    assert {row["fieldPath"] for row in masked} == {"(unknown)", "(unrecognized property)", "person.email"}
    assert {row["reason"] for row in masked} == {"Invalid", "extra_forbidden", "int_parsing"}
    _, full, _ = validation_details(RequestValidationError(errors), route, True)
    assert any(row["reason"] == "bad_custom_reason" for row in full)
    assert any(row["fieldPath"] == "person.email" for row in full)


def test_body_field_is_allowed_only_under_its_declaring_parent() -> None:
    _, diagnostics, _ = validation_details(
        RequestValidationError([{"type": "int_parsing", "loc": ("body", "person", "display_name")}]),
        _route(),
        False,
    )
    assert diagnostics[0]["fieldPath"] == "person[*]"


def test_unresolvable_route_redacts_every_segment_after_location_prefix() -> None:
    # ported: SpringBindingDiagnosticsExtractorTests.extractsJackson3InvalidFormatAndUnrecognizedPropertyAndNeverLeaksValuesInMaskedOrMetadataOnly  # noqa: E501
    _, diagnostics, _ = validation_details(
        RequestValidationError([{"type": "int_parsing", "loc": ("body", "S3NT1NEL", "key")}]), None, False
    )
    assert diagnostics[0]["fieldPath"] == "body[*][*]"


def test_declared_non_body_parameter_names_are_visible_but_unknown_parts_are_redacted() -> None:
    # ported: SpringBindingDiagnosticsExtractorTests.extractsMethodArgumentTypeMismatchAndServerWebInputTypeMismatchWithoutReadingValue  # noqa: E501
    from fastapi import Cookie, Header

    app = FastAPI()

    @app.get("/items/{item_id}")
    def items(
        item_id: int,
        page: int,
        x_region: str = Header(alias="x-region"),
        session: str = Cookie(),
    ) -> None:  # pyright: ignore[reportUnusedFunction]
        return None

    route = app.routes[-1]
    errors = [
        {"type": "int_parsing", "loc": ("query", "page")},
        {"type": "int_parsing", "loc": ("path", "item_id")},
        {"type": "string_type", "loc": ("header", "x-region")},
        {"type": "string_type", "loc": ("cookie", "session")},
        {"type": "int_parsing", "loc": ("query", "S3NT1NEL")},
    ]
    _, diagnostics, _ = validation_details(RequestValidationError(errors), route, False)
    assert {row["fieldPath"] for row in diagnostics} == {
        "query.page",
        "path.item_id",
        "header.x-region",
        "cookie.session",
        "query[*]",
    }


def test_unmodelled_paths_keep_the_location_prefix_and_redact_the_rest() -> None:
    _, diagnostics, _ = validation_details(
        RequestValidationError([{"type": "int_parsing", "loc": ("query", "S3NT1NEL", "other")}]),
        None,
        False,
    )
    assert diagnostics[0]["fieldPath"] == "query[*][*]"


def test_binding_field_path_is_bounded_to_bootui_length() -> None:
    # ported: ExceptionsServiceTests.capsBindingDiagnosticsPerOccurrenceAtTenAndMarksTruncation
    field_name = "field_" + "x" * 300
    model = create_model("WidePayload", **{field_name: (str, ...)})
    route = SimpleNamespace(
        dependant=SimpleNamespace(
            body_params=[SimpleNamespace(name="value", field_info=SimpleNamespace(annotation=model))]
        )
    )

    _, diagnostics, _ = validation_details(
        RequestValidationError([{"type": "string_type", "loc": ("body", field_name)}]), route, True
    )
    assert len(diagnostics[0]["fieldPath"]) == 257


@pytest.mark.parametrize("exposure", ("MASKED", "METADATA_ONLY", "FULL"))
def test_validation_diagnostics_are_safe_and_present_in_occurrence_and_profile(tmp_path: Any, exposure: str) -> None:
    # ported: ExceptionsServiceTests.extractsPerOccurrenceBindingDiagnosticsAndRedactsMapKeysAndUnrecognizedPropertiesExceptInFull  # noqa: E501
    app = FastAPI()

    @app.post("/payload")
    def payload(value: Payload) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": True}

    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        state_dir=str(tmp_path),
        expose_values=exposure,
        mcp_enabled="ON",
        panels={"exceptions": {"enabled": True}},
    )
    try:
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            response = client.post(
                "/payload",
                json={"display_name": "ordinary-secret-91", "person": {"email": "ok"}, "api_token": "raw"},
            )
            listed = client.get("/sharpit/api/exceptions").json()
            group = listed["groups"][0]
            detail = client.get(f"/sharpit/api/exceptions/{group['id']}").json()
            occurrence = detail["occurrences"][0]
            profile = client.get(f"/sharpit/api/activity/request/{occurrence['requestId']}").json()

            def tool_call(name: str, arguments: dict[str, str]) -> str:
                return client.post(
                    "/sharpit/api/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": name, "arguments": arguments},
                    },
                ).text

            mcp = tool_call("get_exception_detail", {"id": group["id"]})
            mcp_profile = tool_call("get_request_profile", {"requestId": occurrence["requestId"]})
            cli = client.post("/sharpit/api/cli/tools/get_exception_detail", json={"id": group["id"]}).text
            cli_profile = client.post(
                "/sharpit/api/cli/tools/get_request_profile", json={"requestId": occurrence["requestId"]}
            ).text
    finally:
        handle.uninstall_capture()

    assert response.status_code == 422
    destinations = {
        "list": str(listed),
        "detail": str(detail),
        "profile": str(profile),
        "mcp": mcp,
        "mcp profile": mcp_profile,
        "cli": cli,
        "cli profile": cli_profile,
    }
    assert all("ordinary-secret-91" not in content for content in destinations.values())
    if exposure != "FULL":
        assert all("api_token" not in content for content in destinations.values())
    assert "bindingDiagnostics" in occurrence
    assert occurrence["bindingDiagnostics"] == [
        {
            "targetType": "Payload",
            "fieldPath": "api_token" if exposure == "FULL" else "(unrecognized property)",
            "reason": "extra_forbidden",
        },
        {"targetType": "Payload", "fieldPath": "display_name", "reason": "int_parsing"},
    ]
    assert occurrence["bindingDiagnosticsTruncated"] is False
    assert profile["exceptions"][0]["bindingDiagnostics"] == occurrence["bindingDiagnostics"]


def test_non_validation_occurrence_emits_empty_binding_diagnostics(tmp_path: Any) -> None:
    # ported: AbstractBootUiApiConformanceTest.validationAndBindingDiagnosticsAreExtractedPerOccurrenceAndScrubbedOnEveryStack  # noqa: E501
    app = FastAPI()

    @app.get("/fail")
    def fail() -> None:  # pyright: ignore[reportUnusedFunction]
        raise RuntimeError("failed")

    handle = install(
        app, enabled="ON", show_banner=False, state_dir=str(tmp_path), panels={"exceptions": {"enabled": True}}
    )
    try:
        with TestClient(
            app, base_url="http://localhost", client=("127.0.0.1", 50000), raise_server_exceptions=False
        ) as client:
            client.get("/fail")
            group = client.get("/sharpit/api/exceptions").json()["groups"][0]
            occurrence = client.get(f"/sharpit/api/exceptions/{group['id']}").json()["occurrences"][0]
    finally:
        handle.uninstall_capture()

    assert occurrence["bindingDiagnostics"] == []
    assert occurrence["bindingDiagnosticsTruncated"] is False


def test_default_422_response_is_byte_identical(tmp_path: Any) -> None:
    # ported: AbstractBootUiApiConformanceTest.validationAndBindingDiagnosticsAreExtractedPerOccurrenceAndScrubbedOnEveryStack  # noqa: E501
    def app_with_route() -> FastAPI:
        app = FastAPI()

        @app.get("/value")
        def value(n: int) -> int:  # pyright: ignore[reportUnusedFunction]
            return n

        return app

    expected = app_with_route()
    app = app_with_route()
    handle = install(
        app, enabled="ON", show_banner=False, state_dir=str(tmp_path), panels={"exceptions": {"enabled": True}}
    )
    try:
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            actual = client.get("/value?n=x")
        with TestClient(expected, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            original = client.get("/value?n=x")
    finally:
        handle.uninstall_capture()
    assert actual.status_code == original.status_code
    assert actual.headers == original.headers
    assert actual.content == original.content


def test_extractor_failure_keeps_the_default_422_response(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    # ported: AbstractBootUiApiConformanceTest.validationAndBindingDiagnosticsAreExtractedPerOccurrenceAndScrubbedOnEveryStack  # noqa: E501
    from sharpit.fastapi import binding_diagnostics

    app = FastAPI()

    @app.get("/value")
    def value(n: int) -> int:  # pyright: ignore[reportUnusedFunction]
        return n

    expected = FastAPI()
    expected.add_api_route("/value", value, methods=["GET"])

    def fail(_exc: BaseException, _endpoint: object, _full: bool) -> Any:
        raise RuntimeError("extractor failed")

    monkeypatch.setattr(binding_diagnostics, "validation_details", fail)
    handle = install(
        app, enabled="ON", show_banner=False, state_dir=str(tmp_path), panels={"exceptions": {"enabled": True}}
    )
    try:
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            actual = client.get("/value?n=x")
        with TestClient(expected, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            original = client.get("/value?n=x")
    finally:
        handle.uninstall_capture()
    assert actual.status_code == original.status_code
    assert actual.headers == original.headers
    assert actual.content == original.content


@pytest.mark.parametrize("registered_after_install", (False, True))
@pytest.mark.parametrize("async_handler", (False, True))
def test_replaced_422_handlers_remain_byte_identical(
    tmp_path: Any, registered_after_install: bool, async_handler: bool
) -> None:
    # ported: AbstractBootUiApiConformanceTest.validationAndBindingDiagnosticsAreExtractedPerOccurrenceAndScrubbedOnEveryStack  # noqa: E501
    def handler(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"host": "response"}, 422, headers={"X-Host": "kept"})

    async def async_handler_fn(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"host": "response"}, 422, headers={"X-Host": "kept"})

    selected = async_handler_fn if async_handler else handler

    def app_with_route(custom: bool) -> FastAPI:
        app = FastAPI()
        if custom and not registered_after_install:
            app.add_exception_handler(RequestValidationError, selected)

        @app.get("/value")
        def value(n: int) -> int:  # pyright: ignore[reportUnusedFunction]
            return n

        if custom and registered_after_install:
            app.add_exception_handler(RequestValidationError, selected)
        return app

    app = app_with_route(not registered_after_install)
    expected = app_with_route(True)
    handle = install(
        app, enabled="ON", show_banner=False, state_dir=str(tmp_path), panels={"exceptions": {"enabled": True}}
    )
    if registered_after_install:
        app.add_exception_handler(RequestValidationError, selected)
    try:
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            actual = client.get("/value?n=x")
        with TestClient(expected, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            original = client.get("/value?n=x")
    finally:
        handle.uninstall_capture()
    assert actual.status_code == original.status_code
    assert actual.headers == original.headers
    assert actual.content == original.content


@pytest.mark.parametrize("exposure", ("MASKED", "METADATA_ONLY", "FULL"))
def test_invalid_path_parameter_exception_path_follows_exposure(
    tmp_path: Any, exposure: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sharpit.fastapi import capture

    recorded_request_paths: list[str] = []
    record_exception = capture._record_exception

    def observe_record(*args: Any, **kwargs: Any) -> None:
        info = args[3]
        record_exception(*args, **kwargs)
        if info is not None:
            recorded_request_paths.append(info.path)

    monkeypatch.setattr(capture, "_record_exception", observe_record)
    app = FastAPI()

    @app.get("/items/{item_id}")
    def item(item_id: int) -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        return {"item_id": item_id}

    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        state_dir=str(tmp_path / exposure),
        expose_values=exposure,
        panels={"exceptions": {"enabled": True}},
    )
    try:
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            response = client.get("/items/S3NT1NEL9f3c")
            groups = client.get("/sharpit/api/exceptions").json()["groups"]
            occurrence = client.get(f"/sharpit/api/exceptions/{groups[0]['id']}").json()["occurrences"][0]
            profile = client.get(f"/sharpit/api/activity/request/{occurrence['requestId']}").json()
    finally:
        handle.uninstall_capture()

    assert response.status_code == 422
    expected = "/items/S3NT1NEL9f3c" if exposure == "FULL" else "/items/{item_id}"
    assert groups[0]["lastRequestPath"] == expected
    assert profile["request"]["path"] == "/items/S3NT1NEL9f3c"
    assert occurrence["requestPath"] == expected
    if exposure != "FULL":
        assert "/items/S3NT1NEL9f3c" in recorded_request_paths
