"""Declaration-only error-contract catalog."""

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

from sharpit.engine.appsource import ModuleInfo, SourceIndex
from sharpit.engine.collectors.restapi.error_contract import entries, error_contract_report


def _model(*handlers: tuple[str | None, int | None, str, str, str | None]) -> SimpleNamespace:
    return SimpleNamespace(
        error_handlers=tuple(
            SimpleNamespace(
                key_type=key_type,
                key_status=key_status,
                handler=handler,
                scope=scope,
                scope_target=target,
            )
            for key_type, key_status, handler, scope, target in handlers
        ),
        limitations=(),
    )


def _index(source: str) -> SourceIndex:
    tree = ast.parse(source)
    return SourceIndex(modules={"app.errors": ModuleInfo("app.errors", Path("errors.py"), tree, (), ())})


def test_an_application_without_handlers_is_available_and_empty() -> None:
    # ported: ErrorContractServiceTests.anApplicationWithoutHandlersIsAvailableAndEmpty
    report = error_contract_report(_model(), None, None, 0, None)
    assert report["available"] is True
    assert report["entries"] == []


def test_one_declaration_per_handled_exception_type_is_catalogued() -> None:
    # ported: ErrorContractServiceTests.oneDeclarationPerHandledExceptionTypeIsCatalogued
    result = entries(_model(("example.NotFound", None, "app.errors:handle", "GLOBAL", None)), None)
    assert len(result) == 1
    assert result[0].exception_type == "example.NotFound"


def test_a_controller_local_handler_outranks_an_application_wide_one() -> None:
    # ported: ErrorContractServiceTests.aControllerLocalHandlerOutranksAnApplicationWideOne
    result = entries(
        _model(
            ("example.Failure", None, "app.errors:global_handler", "GLOBAL", None),
            ("example.Failure", None, "app.orders:local_handler", "SCOPED", "/orders"),
        ),
        None,
    )
    assert len(result) == 2
    assert [(item.scope, item.precedence, item.precedence_source) for item in result] == [
        ("SCOPED", 1, "DEFAULT"),
        ("GLOBAL", 2, "DEFAULT"),
    ]


def test_body_categories_are_derived_from_the_declaration_only() -> None:
    # ported: ErrorContractServiceTests.bodyCategoriesAreDerivedFromTheDeclarationOnly
    source = """
from starlette.responses import JSONResponse, PlainTextResponse, Response
def problem(): return JSONResponse({"type": "about:blank", "title": "Failure", "status": 400})
def custom(): return JSONResponse({"error": "Failure"})
def text(): return PlainTextResponse("Failure")
def empty(): return Response()
def dynamic(): return JSONResponse(payload)
"""
    handlers = [
        ("example.Failure", None, f"app.errors:{name}", "GLOBAL", None)
        for name in ("problem", "custom", "text", "empty", "dynamic")
    ]
    result = entries(_model(*handlers), _index(source))
    assert [item.body_category for item in result] == ["CUSTOM_OBJECT", "DYNAMIC", "EMPTY", "PROBLEM_DETAIL", "STRING"]


def test_a_declared_status_is_reported_as_annotation_sourced_and_a_runtime_status_stays_dynamic() -> None:
    # ported: ErrorContractServiceTests.aDeclaredStatusIsReportedAsAnnotationSourcedAndARuntimeStatusStaysDynamic
    source = """
from starlette.responses import JSONResponse
def annotated(): return JSONResponse({}, status_code=404)
def dynamic(): return JSONResponse({}, status_code=status)
"""
    result = entries(
        _model(
            ("example.NotFound", None, "app.errors:annotated", "GLOBAL", None),
            ("example.Conflict", None, "app.errors:dynamic", "GLOBAL", None),
        ),
        _index(source),
    )
    assert len(result) == 2
    annotated = next(item for item in result if item.exception_type == "example.NotFound")
    dynamic = next(item for item in result if item.exception_type == "example.Conflict")
    assert annotated.status == "404"
    assert annotated.status_source == "ANNOTATION"
    assert dynamic.status is None
    assert dynamic.status_source == "DYNAMIC"


def test_the_query_and_paging_run_on_the_server() -> None:
    # ported: ErrorContractServiceTests.theQueryAndPagingRunOnTheServer
    model = _model(*[(f"example.Failure{i}", None, f"app.errors:handle{i}", "GLOBAL", None) for i in range(12)])
    page = error_contract_report(model, None, "Failure7", 0, 5)
    assert len(page["entries"]) == 1
    assert page["page"]["matched"] == 1


def test_the_catalogue_is_bounded_and_says_so_when_it_truncates() -> None:
    # ported: ErrorContractServiceTests.theCatalogueIsBoundedAndSaysSoWhenItTruncates
    model = _model(*[(f"example.Failure{i}", None, f"app.errors:handle{i}", "GLOBAL", None) for i in range(501)])
    report = error_contract_report(model, None, None, 0, None)
    assert report["maxEntries"] == 500
    assert report["truncated"] is True


def test_error_contract_never_emits_handler_literals() -> None:
    source = 'def handle(): return {"detail": "secret-password"}'
    model = _model(("example.Failure", None, "app.errors:handle", "GLOBAL", None))
    report = error_contract_report(model, _index(source), None, 0, None)
    assert report["available"] is True
    assert "secret-password" not in repr(report)


def test_handler_body_reads_only_the_source_index(monkeypatch) -> None:
    model = _model(("example.Failure", None, "app.errors:handle", "GLOBAL", None))
    monkeypatch.setattr(inspect, "getsource", lambda *_args: (_ for _ in ()).throw(AssertionError("source read")))
    result = entries(model, _index('def handle(): return "body"'))
    assert len(result) == 1
    assert result[0].body_category == "STRING"


def test_handler_body_resolves_the_full_nested_qualname() -> None:
    source = "def handle(): return {'type': 'about:blank', 'title': 'Wrong', 'status': 400}\nclass Outer:\n    def handle(): return 'right'\n"
    result = entries(_model(("example.Failure", None, "app.errors:Outer.handle", "GLOBAL", None)), _index(source))
    assert result[0].body_category == "STRING"


def test_error_contract_unresolved_handler_is_partial() -> None:
    model = _model(("example.Failure", None, "app.errors:partial_handler", "GLOBAL", None))
    result = entries(model, None)
    assert len(result) == 1
    assert result[0].body_category == "UNRESOLVED"


def test_bound_partial_handler_stays_unresolved_even_with_source_index() -> None:
    model = _model(("example.Failure", None, "app.errors:handle", "GLOBAL", None))
    model.error_handlers[0].is_partial = True
    result = entries(model, _index('def handle(): return "body"'))
    assert result[0].body_category == "UNRESOLVED"


def test_error_contract_sorts_by_exception_simple_name() -> None:
    result = entries(
        _model(
            ("z.Zebra", None, "app.errors:z", "GLOBAL", None),
            ("a.Alpha", None, "app.errors:a", "GLOBAL", None),
        ),
        None,
    )
    assert [item.exception_simple_name for item in result] == ["Alpha", "Zebra"]


def test_error_contract_uses_positional_response_status() -> None:
    source = """
from starlette.responses import JSONResponse, Response
def json_error(): return JSONResponse({}, 400)
def plain_error(): return Response(b'', 404)
"""
    result = entries(
        _model(
            ("a.JsonError", None, "app.errors:json_error", "GLOBAL", None),
            ("b.PlainError", None, "app.errors:plain_error", "GLOBAL", None),
        ),
        _index(source),
    )
    assert [item.status for item in result] == ["400", "404"]
