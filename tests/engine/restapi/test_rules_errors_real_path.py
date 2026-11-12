"""RAPI-ERR rules driven through the real path: handler source -> AST -> error-contract entry -> rule.

No hand-built ``ErrorContractEntry``: each handler is a real function in this module, registered on a real FastAPI app,
read by ``FastApiIntrospector`` and ``assess()``. No ``from __future__ import annotations`` (handler annotations).
"""

import email  # noqa: F401 - a loaded package that does not contain the handlers below (app_package for the index test)
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.restapi.rules import RULES, violations
from sharpit.engine.collectors.restapi.service import assess
from sharpit.engine.masking import Exposure, Masker
from sharpit.fastapi.introspector import FastApiIntrospector


def _compute() -> int:
    return 400


def _hdrs() -> dict[str, str]:
    return {"Retry-After": "5"}


def no_status(_request: object, _exc: ValueError) -> JSONResponse:
    return JSONResponse({"a": 1})


def dynamic_status(_request: object, _exc: KeyError) -> JSONResponse:
    return JSONResponse({"a": 1}, status_code=_compute())


def bool_status(_request: object, _exc: LookupError) -> JSONResponse:
    return JSONResponse({"a": 1}, status_code=True)


def problem_no_status(_request: object, _exc: OSError) -> JSONResponse:
    return JSONResponse({"type": "about:blank", "title": "Bad", "status": 400})


def broad_problem(_request: object, _exc: Exception) -> JSONResponse:
    return JSONResponse({"type": "about:blank", "title": "Bad", "status": 400}, status_code=400)


def broad_plain(_request: object, _exc: BaseException) -> JSONResponse:
    return JSONResponse({"error": "bad"}, status_code=400)


def throttle_plain(_request: object, _exc: ValueError) -> JSONResponse:
    return JSONResponse({"a": 1}, status_code=429)


def throttle_other_header(_request: object, _exc: KeyError) -> JSONResponse:
    return JSONResponse({"a": 1}, status_code=429, headers={"X-Other": "1"})


def throttle_literal_header(_request: object, _exc: LookupError) -> JSONResponse:
    return JSONResponse({"a": 1}, status_code=429, headers={"Retry-After": "5"})


def throttle_lower_header(_request: object, _exc: OSError) -> JSONResponse:
    return JSONResponse({"a": 1}, status_code=503, headers={"retry-after": "5"})


def throttle_positional_header(_request: object, _exc: ArithmeticError) -> JSONResponse:
    return JSONResponse({"a": 1}, 503, {"Retry-After": "5"})


def throttle_dynamic_header(_request: object, _exc: RuntimeError) -> JSONResponse:
    return JSONResponse({"a": 1}, status_code=503, headers=_hdrs())


def _app(*handlers: object) -> FastAPI:
    app = FastAPI(openapi_url=None)

    @app.get("/items", summary="s", tags=["t"])
    def get_items() -> list[int]:
        return []

    for handler in handlers:
        app.exception_handlers[_key(handler)] = handler  # type: ignore[assignment]
    return app


def _key(handler: object) -> type[BaseException]:
    return getattr(handler, "__annotations__")["_exc"]  # noqa: B009 - the annotated exception class


def _targets(app: FastAPI, rule_id: str) -> list[str]:
    run = assess(FastApiIntrospector(app).api_model(), Masker(Exposure.MASKED, True))
    return sorted(f.target for f in run.findings if f.rule_id == rule_id)


def _names(targets: list[str]) -> list[str]:
    return [t.rpartition(".")[2].rpartition("#")[2] for t in targets]


# --- finding 1: ERR-004 fires only when no status is visible -----------------------------------------------------


def test_err004_skips_a_dynamic_status_and_flags_a_missing_one() -> None:
    app = _app(no_status, dynamic_status, bool_status)
    assert _names(_targets(app, "RAPI-ERR-004")) == ["no_status"]


# --- finding 2: ERR-007 reads Retry-After headers ----------------------------------------------------------------


def test_err007_skips_handlers_that_set_retry_after_or_build_headers_dynamically() -> None:
    app = _app(
        throttle_plain,
        throttle_other_header,
        throttle_literal_header,
        throttle_lower_header,
        throttle_positional_header,
        throttle_dynamic_header,
    )
    found = _targets(app, "RAPI-ERR-007")
    assert _names(found) == ["throttle_other_header", "throttle_plain"]


# --- finding 3: problem-detail bodies are skipped ----------------------------------------------------------------


def test_err004_skips_a_problem_detail_body() -> None:
    app = _app(problem_no_status)
    assert _targets(app, "RAPI-ERR-004") == []


def test_err005_skips_a_problem_detail_body() -> None:
    app = _app(broad_problem)
    assert _targets(app, "RAPI-ERR-005") == []


# --- finding 4: Python wording ----------------------------------------------------------------------------------


def test_err005_message_and_text_name_exception_and_baseexception() -> None:
    app = _app(broad_plain)
    run = assess(FastApiIntrospector(app).api_model(), Masker(Exposure.MASKED, True))
    (message,) = [f.message for f in run.findings if f.rule_id == "RAPI-ERR-005"]
    assert "catches Exception/BaseException and maps it" in message
    rule = next(r for r in RULES if r.id == "RAPI-ERR-005")
    assert "Throwable" not in rule.description
    assert "Throwable" not in rule.recommendation


# --- finding 9: BootUI's help link and punctuation ---------------------------------------------------------------


@pytest.mark.parametrize("rule_id", ["RAPI-ERR-004", "RAPI-ERR-005"])
def test_exception_handler_rules_link_the_exception_handler_docs(rule_id: str) -> None:
    rule = next(r for r in RULES if r.id == rule_id)
    assert rule.learn_more_url == "https://fastapi.tiangolo.com/tutorial/handling-errors/"


def test_err007_route_violation_has_no_dash() -> None:
    app = FastAPI(openapi_url=None)

    @app.get("/slow", status_code=429, summary="s", tags=["t"])
    def slow() -> list[int]:
        return []

    model = FastApiIntrospector(app).api_model()
    (message,) = violations(model.routes, ())["RAPI-ERR-007"]
    assert message.endswith("] declares 429; optionally review Retry-After policy")


# --- finding 7: the rules read the same index as the error-contract panel -----------------------------------------


def test_scan_and_panel_resolve_the_same_handlers(tmp_path: Path) -> None:
    app = _app(no_status)
    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        config_scan=False,
        app_package="email",
        state_dir=str(tmp_path / "state"),
    )
    try:
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            entries = client.get("/sharpit/api/rest-api/error-contract").json()["entries"]
            scan = client.post("/sharpit/api/rest-api/scan").json()
        assert [e["bodyCategory"] for e in entries] == ["UNRESOLVED"]  # the app package holds no handler source
        assert "RAPI-ERR-004" not in {r["id"] for r in scan["results"]}  # the scan lists violating rules only
    finally:
        handle.uninstall_capture()
