"""FastAPI binding diagnostics; source parity is cited at each ported behavior."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict
from starlette.requests import Request
from starlette.responses import JSONResponse

from sharpit import install


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: int


def test_validation_diagnostics_are_safe_and_present_in_occurrence_and_profile(tmp_path: Any) -> None:
    # ported: ExceptionsServiceTests.extractsPerOccurrenceBindingDiagnosticsAndRedactsMapKeysAndUnrecognizedPropertiesExceptInFull
    # ported: ExceptionsServiceTests.extractsPerOccurrenceBindingDiagnosticsAndRedactsMapKeysAndUnrecognizedPropertiesExceptInFull
    app = FastAPI()

    @app.post("/payload")
    def payload(value: Payload) -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        return {"ok": True}

    handle = install(app, enabled="ON", show_banner=False, state_dir=str(tmp_path), panels={"exceptions": {"enabled": True}})
    try:
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            response = client.post("/payload", json={"display_name": "ordinary-secret-91", "api_token": "raw"})
            listed = client.get("/sharpit/api/exceptions").json()
            group = listed["groups"][0]
            detail = client.get(f"/sharpit/api/exceptions/{group['id']}").json()
            occurrence = detail["occurrences"][0]
            profile = client.get(f"/sharpit/api/activity/request/{occurrence['requestId']}").json()
    finally:
        handle.uninstall_capture()

    assert response.status_code == 422
    assert "ordinary-secret-91" not in str(listed)
    assert "api_token" not in str(detail)
    assert "bindingDiagnostics" in occurrence
    assert occurrence["bindingDiagnostics"] == [
        {"targetType": "Payload", "fieldPath": "display_name", "reason": "int_parsing"},
        {"targetType": "Payload", "fieldPath": "(unrecognized property)", "reason": "extra_forbidden"},
    ]
    assert occurrence["bindingDiagnosticsTruncated"] is False
    assert profile["exceptions"][0]["bindingDiagnostics"] == occurrence["bindingDiagnostics"]


def test_non_validation_occurrence_emits_empty_binding_diagnostics(tmp_path: Any) -> None:
    # ported: AbstractBootUiApiConformanceTest.validationAndBindingDiagnosticsAreExtractedPerOccurrenceAndScrubbedOnEveryStack
    # ported: AbstractBootUiApiConformanceTest.validationAndBindingDiagnosticsAreExtractedPerOccurrenceAndScrubbedOnEveryStack
    app = FastAPI()

    @app.get("/fail")
    def fail() -> None:  # pyright: ignore[reportUnusedFunction]
        raise RuntimeError("failed")

    handle = install(app, enabled="ON", show_banner=False, state_dir=str(tmp_path), panels={"exceptions": {"enabled": True}})
    try:
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000), raise_server_exceptions=False) as client:
            client.get("/fail")
            group = client.get("/sharpit/api/exceptions").json()["groups"][0]
            occurrence = client.get(f"/sharpit/api/exceptions/{group['id']}").json()["occurrences"][0]
    finally:
        handle.uninstall_capture()

    assert occurrence["bindingDiagnostics"] == []
    assert occurrence["bindingDiagnosticsTruncated"] is False


def test_custom_validation_handler_response_is_preserved(tmp_path: Any) -> None:
    app = FastAPI()

    @app.exception_handler(Exception)
    async def custom(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse({"host": "response"}, 422, headers={"X-Host": "kept"})

    @app.get("/value")
    def value(n: int) -> int:  # pyright: ignore[reportUnusedFunction]
        return n

    expected = FastAPI()
    expected.add_api_route("/value", value, methods=["GET"])
    expected.add_exception_handler(Exception, custom)

    handle = install(app, enabled="ON", show_banner=False, state_dir=str(tmp_path), panels={"exceptions": {"enabled": True}})
    try:
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as actual_client:
            actual = actual_client.get("/value?n=x")
        with TestClient(expected, base_url="http://localhost", client=("127.0.0.1", 50000)) as expected_client:
            original = expected_client.get("/value?n=x")
    finally:
        handle.uninstall_capture()

    assert actual.status_code == original.status_code
    assert actual.headers == original.headers
    assert actual.content == original.content
