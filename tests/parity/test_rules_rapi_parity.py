"""REST API advisor rule parity against BootUI 2.3.0 ``RAPI-*`` rules.

Each rule gets a FastAPI analogue of the BootUI fixture: one case where it fires and one where it does not, asserting
what BootUI asserts (status, the 2.3.0 severity, the handler named in the violation). The app is read through
``FastApiIntrospector.api_model()`` and ``assess()``, the same path the panel and the pytest plugin take. No
module-level ``from __future__ import annotations``: handler annotations must resolve as real types.
"""

from typing import Annotated, Any, ClassVar, Optional

import pytest
from pydantic import BaseModel
from starlette.responses import JSONResponse, PlainTextResponse

from fastapi import Body, FastAPI, Response
from sharpit.engine.advisors.findings import Finding
from sharpit.engine.collectors.restapi.service import assess
from sharpit.engine.masking import Exposure, Masker
from sharpit.fastapi.introspector import FastApiIntrospector


class Payload(BaseModel):
    id: str
    name: str


class OrderEntity:
    """A persistence class (SQLModel ``table=True`` / SQLAlchemy declarative), duck-typed like BootUI's ``@Entity``."""

    __table__: ClassVar[object] = object()


def _findings(app: FastAPI, rule_id: str) -> list[Finding]:
    run = assess(FastApiIntrospector(app).api_model(), Masker(Exposure.MASKED, True))
    return [f for f in run.findings if f.rule_id == rule_id]


def _one(app: FastAPI, rule_id: str, severity: str) -> Finding:
    found = _findings(app, rule_id)
    assert len(found) == 1, [f.message for f in found]
    finding = found[0]
    assert finding.severity == severity
    return finding


def _located(finding: Finding, method: str, path: str, function: str) -> None:
    """The location BootUI asserts (``Class#method``): the method, path and handler function, never a value."""
    assert finding.target.startswith(f"{method} {path} ")
    assert finding.target.endswith(f".{function}") or finding.target.endswith(f":{function}")
    assert function in finding.message


def _app(*, openapi_url: str | None = "/openapi.json") -> FastAPI:
    return FastAPI(openapi_url=openapi_url)


# --- Routing & HTTP method mapping ---------------------------------------------------------------------------------


@pytest.mark.bootui("rule:RAPI-MAP-001")
def test_rapi_map_001_fires_on_get_combined_with_a_mutating_method() -> None:
    # ported: RestApiRulesTests.routingRulesFlagBadController
    # BadOrderController#legacy: @RequestMapping("/legacy") with no method constraint (FastAPI: one route, GET + POST)
    app = _app()

    @app.api_route("/legacy", methods=["GET", "POST"], summary="s", tags=["t"])
    def legacy() -> Payload:
        return Payload(id="1", name="n")

    finding = _one(app, "RAPI-MAP-001", "MEDIUM")
    assert finding.target.startswith("GET /legacy | POST /legacy ")
    assert finding.target.endswith(".legacy")


@pytest.mark.bootui("rule:RAPI-MAP-001")
def test_rapi_map_001_passes_an_explicit_method_mapping() -> None:
    # ported: RestApiRulesTests.classLevelRequestMappingMethodIsInherited
    app = _app()

    @app.get("/typed/{item_id}", summary="s", tags=["t"])
    def read(item_id: str) -> Payload:
        return Payload(id=item_id, name="n")

    assert _findings(app, "RAPI-MAP-001") == []


@pytest.mark.bootui("rule:RAPI-MAP-002")
def test_rapi_map_002_fires_on_two_handlers_for_one_method_and_path() -> None:
    # ported: RestApiRuleAccuracyTests.duplicateRoutesReportOnlySpringMappingsThatRegisterAndFailAtRequestTime
    # OverlappingMethodSets: the one sample names "GET /overlap", "#any" and "#read"
    app = _app()

    @app.get("/overlap", summary="s", tags=["t"])
    def any_items() -> Payload:
        return Payload(id="1", name="n")

    @app.get("/overlap", summary="s", tags=["t"])
    def read() -> Payload:
        return Payload(id="1", name="n")

    finding = _one(app, "RAPI-MAP-002", "HIGH")
    assert finding.target == "GET /overlap"
    assert "GET /overlap" in finding.message
    assert ".any_items" in finding.message
    assert ".read" in finding.message


@pytest.mark.bootui("rule:RAPI-MAP-002")
def test_rapi_map_002_passes_distinct_routes() -> None:
    # ported: RestApiRulesTests.modelAccuracyFixturesAvoidFalsePositivesAndExposeExplicitPathVariableMismatches
    app = _app()

    @app.get("/overlap", summary="s", tags=["t"])
    def read() -> Payload:
        return Payload(id="1", name="n")

    @app.post("/overlap", status_code=201, summary="s", tags=["t"])
    def create(body: Payload) -> Payload:
        return body

    @app.get("/overlap/", summary="s", tags=["t"])  # BootUI: route identity keeps trailing slashes
    def read_slash() -> Payload:
        return Payload(id="1", name="n")

    assert _findings(app, "RAPI-MAP-002") == []


@pytest.mark.bootui("rule:RAPI-MAP-003")
def test_rapi_map_003_fires_on_a_mutation_like_get_name() -> None:
    # ported: RestApiRulesTests.stateChangingNameMatchingAvoidsAmbiguousHttpVerbPrefixesOnSpring
    app = _app()

    @app.get("/widgets/{widget_id}/touch", summary="s", tags=["t"])
    def update_widget(widget_id: str) -> Payload:
        return Payload(id=widget_id, name="n")

    finding = _one(app, "RAPI-MAP-003", "LOW")
    _located(finding, "GET", "/widgets/{widget_id}/touch", "update_widget")


@pytest.mark.bootui("rule:RAPI-MAP-003")
def test_rapi_map_003_passes_ambiguous_http_verb_prefixes() -> None:
    # ported: RestApiRulesTests.stateChangingNameMatchingAvoidsAmbiguousHttpVerbPrefixesOnSpring
    # ported: RestApiRulesTests.routingRulesFlagBadController
    app = _app()

    @app.get("/a", summary="s", tags=["t"])
    def post_process() -> Payload:
        return Payload(id="1", name="n")

    @app.get("/b", summary="s", tags=["t"])
    def put_aside() -> Payload:
        return Payload(id="1", name="n")

    @app.get("/c", summary="s", tags=["t"])
    def patch_version() -> Payload:
        return Payload(id="1", name="n")

    assert _findings(app, "RAPI-MAP-003") == []


@pytest.mark.bootui("rule:RAPI-MAP-005")
def test_rapi_map_005_fires_on_a_trailing_slash() -> None:
    # ported: RestApiRulesTests.routingRulesFlagBadController
    # BadOrderController#getOrder: @GetMapping("/Orders/{id}/")
    app = _app()

    @app.get("/orders/{order_id}/", summary="s", tags=["t"])
    def get_order(order_id: str) -> Payload:
        return Payload(id=order_id, name="n")

    finding = _one(app, "RAPI-MAP-005", "INFO")
    _located(finding, "GET", "/orders/{order_id}/", "get_order")


@pytest.mark.bootui("rule:RAPI-MAP-005")
def test_rapi_map_005_passes_clean_paths() -> None:
    # BootUI 2.3.0 has no does-not-fire case for ConsistentPathStyleRule (cleanControllerPassesCoreRules omits it)
    app = _app()

    @app.get("/api/v1/users/{user_id}", summary="s", tags=["t"])
    def get_user(user_id: str) -> Payload:
        return Payload(id=user_id, name="n")

    assert _findings(app, "RAPI-MAP-005") == []


@pytest.mark.bootui("rule:RAPI-MAP-007")
def test_rapi_map_007_fires_on_a_request_body_on_delete() -> None:
    # ported: RestApiRulesTests.routingEdgeRulesFlagPathVariableAndBodyMisuse
    # EdgeCaseController#removeWidget: @DeleteMapping with @RequestBody
    app = _app()

    @app.delete("/api/v2/widgets/{widget_id}", status_code=204, summary="s", tags=["t"])
    def remove_widget(widget_id: str, body: Payload) -> None:
        return None

    finding = _one(app, "RAPI-MAP-007", "MEDIUM")
    _located(finding, "DELETE", "/api/v2/widgets/{widget_id}", "remove_widget")


@pytest.mark.bootui("rule:RAPI-MAP-007")
def test_rapi_map_007_passes_a_bodyless_delete() -> None:
    # ported: RestApiRulesTests.cleanControllerPassesNewerRules
    app = _app()

    @app.delete("/api/v1/users/{user_id}", status_code=204, summary="s", tags=["t"])
    def delete_user(user_id: str) -> None:
        return None

    assert _findings(app, "RAPI-MAP-007") == []


@pytest.mark.bootui("rule:RAPI-MAP-010")
def test_rapi_map_010_fires_on_a_catch_all_path() -> None:
    # ported: RestApiRulesTests.phase3NewRulesFlagBadController
    # Phase3BadController#catchAll: @GetMapping("/**") (FastAPI: a ``:path`` converter)
    app = _app()

    @app.get("/api/phase3/{rest:path}", summary="s", tags=["t"])
    def catch_all(rest: str) -> Payload:
        return Payload(id=rest, name="n")

    finding = _one(app, "RAPI-MAP-010", "INFO")
    _located(finding, "GET", "/api/phase3/{rest:path}", "catch_all")


@pytest.mark.bootui("rule:RAPI-MAP-010")
def test_rapi_map_010_passes_plain_variables() -> None:
    # ported: RestApiRulesTests.phase3NewRulesPassGoodController
    app = _app()

    @app.get("/api/v1/users/{user_id}/orders/{order_id}", summary="s", tags=["t"])
    def get_order(user_id: str, order_id: str) -> Payload:
        return Payload(id=order_id, name="n")

    assert _findings(app, "RAPI-MAP-010") == []


@pytest.mark.bootui("rule:RAPI-MAP-011")
def test_rapi_map_011_fires_on_four_levels_of_nesting() -> None:
    # ported: RestApiRulesTests.phase3NewRulesFlagBadController
    app = _app()

    @app.get("/api/phase3/a/{a_id}/b/{b_id}/c/{c_id}/d/{d_id}", summary="s", tags=["t"])
    def deep_nesting(a_id: str, b_id: str, c_id: str, d_id: str) -> Payload:
        return Payload(id=a_id, name="n")

    finding = _one(app, "RAPI-MAP-011", "INFO")
    _located(finding, "GET", "/api/phase3/a/{a_id}/b/{b_id}/c/{c_id}/d/{d_id}", "deep_nesting")


@pytest.mark.bootui("rule:RAPI-MAP-011")
def test_rapi_map_011_passes_two_levels_of_nesting() -> None:
    # ported: RestApiRulesTests.phase3NewRulesPassGoodController
    app = _app()

    @app.get("/api/v1/users/{user_id}/orders/{order_id}", summary="s", tags=["t"])
    def get_order(user_id: str, order_id: str) -> Payload:
        return Payload(id=order_id, name="n")

    assert _findings(app, "RAPI-MAP-011") == []


# --- Naming & resource design --------------------------------------------------------------------------------------


@pytest.mark.bootui("rule:RAPI-NAME-001")
def test_rapi_name_001_fires_on_a_verb_in_the_path() -> None:
    # ported: RestApiRulesTests.namingRulesFlagVerbsAndCase
    # BadOrderController#getOrders: @GetMapping("/getOrders")
    app = _app()

    @app.get("/getOrders", summary="s", tags=["t"])
    def get_orders(limit: int = 10) -> list[Payload]:
        return []

    finding = _one(app, "RAPI-NAME-001", "INFO")
    _located(finding, "GET", "/getOrders", "get_orders")


@pytest.mark.bootui("rule:RAPI-NAME-001")
def test_rapi_name_001_passes_an_ambiguous_noun() -> None:
    # ported: RestApiRulesTests.name001DoesNotFlagAmbiguousNounSegments
    # ported: RestApiRulesTests.cleanControllerPassesCoreRules
    app = _app()

    @app.get("/api/v1/blog/post/{post_id}", summary="s", tags=["t"])
    def get_blog_post(post_id: str) -> Payload:
        return Payload(id=post_id, name="n")

    assert _findings(app, "RAPI-NAME-001") == []


@pytest.mark.bootui("rule:RAPI-NAME-002")
def test_rapi_name_002_passes_an_uncountable_collection() -> None:
    # ported: RestApiRulesTests.name002DoesNotFlagUncountableNouns
    # BootUI 2.3.0 asserts only this does-not-fire case for NAME-002 (no ported firing case exists)
    app = _app()

    @app.get("/api/v1/history", summary="s", tags=["t"])
    def get_history(limit: int = 10) -> list[Payload]:
        return []

    assert _findings(app, "RAPI-NAME-002") == []


@pytest.mark.bootui("rule:RAPI-NAME-003")
def test_rapi_name_003_fires_on_a_non_kebab_segment() -> None:
    # ported: RestApiRulesTests.namingRulesFlagVerbsAndCase
    # BadOrderController#getOrder: @GetMapping("/Orders/{id}/")
    app = _app()

    @app.get("/Orders/{order_id}", summary="s", tags=["t"])
    def get_order(order_id: str) -> Payload:
        return Payload(id=order_id, name="n")

    finding = _one(app, "RAPI-NAME-003", "INFO")
    _located(finding, "GET", "/Orders/{order_id}", "get_order")
    assert "'Orders'" in finding.message


@pytest.mark.bootui("rule:RAPI-NAME-003")
def test_rapi_name_003_passes_kebab_case_and_variables() -> None:
    # ported: RestApiRulesTests.modelAccuracyFixturesAvoidFalsePositivesAndExposeExplicitPathVariableMismatches
    app = _app()

    @app.get("/api/v1/pet-types/{pet_type_id}", summary="s", tags=["t"])
    def get_pet_type(pet_type_id: str) -> Payload:
        return Payload(id=pet_type_id, name="n")

    assert _findings(app, "RAPI-NAME-003") == []


# --- Status codes & responses --------------------------------------------------------------------------------------


@pytest.mark.bootui("rule:RAPI-RESP-001")
def test_rapi_resp_001_fires_on_a_creation_post_with_the_default_status() -> None:
    # ported: RestApiRuleAccuracyTests.responseRulesRespectExplicitDynamicAndImperativeStatusSelection
    # ported: RestApiRulesTests.responseRulesFlagCreationAndScalarReads
    app = _app()

    @app.post("/rule-accuracy/default", summary="s", tags=["t"])
    def create_default(body: Payload) -> Payload:
        return body

    finding = _one(app, "RAPI-RESP-001", "LOW")
    _located(finding, "POST", "/rule-accuracy/default", "create_default")


@pytest.mark.bootui("rule:RAPI-RESP-001")
def test_rapi_resp_001_passes_explicit_and_dynamic_status_selection() -> None:
    # ported: RestApiRuleAccuracyTests.responseRulesRespectExplicitDynamicAndImperativeStatusSelection
    # ported: RestApiRulesTests.cleanControllerPassesCoreRules
    app = _app()

    @app.post("/rule-accuracy/accepted", status_code=202, summary="s", tags=["t"])
    def create_accepted(body: Payload) -> Payload:
        return body

    @app.post("/rule-accuracy/imperative", summary="s", tags=["t"])
    def create_imperative(body: Payload, response: Response) -> Payload:
        response.status_code = 201
        return body

    assert _findings(app, "RAPI-RESP-001") == []


@pytest.mark.bootui("rule:RAPI-RESP-002")
def test_rapi_resp_002_fires_on_a_default_empty_delete() -> None:
    # ported: RestApiRuleAccuracyTests.responseRulesRespectExplicitDynamicAndImperativeStatusSelection
    app = _app()

    @app.delete("/rule-accuracy/empty", summary="s", tags=["t"])
    def delete_default() -> None:
        return None

    finding = _one(app, "RAPI-RESP-002", "LOW")
    _located(finding, "DELETE", "/rule-accuracy/empty", "delete_default")


@pytest.mark.bootui("rule:RAPI-RESP-002")
def test_rapi_resp_002_passes_explicit_and_imperative_status() -> None:
    # ported: RestApiRuleAccuracyTests.responseRulesRespectExplicitDynamicAndImperativeStatusSelection
    # ported: RestApiRulesTests.cleanControllerPassesCoreRules
    app = _app()

    @app.delete("/rule-accuracy/accepted", status_code=202, summary="s", tags=["t"])
    def delete_accepted() -> None:
        return None

    @app.delete("/rule-accuracy/imperative", summary="s", tags=["t"])
    def delete_imperative(response: Response) -> None:
        response.status_code = 204

    @app.delete("/api/v1/users/{user_id}", status_code=204, summary="s", tags=["t"])
    def delete_user(user_id: str) -> None:
        return None

    assert _findings(app, "RAPI-RESP-002") == []


def _no_content_body_app() -> FastAPI:
    app = _app()

    @app.get("/rule-accuracy/contradiction", status_code=204, response_model=None, summary="s", tags=["t"])
    def no_content_body() -> Payload:
        return Payload(id="1", name="n")

    return app


@pytest.mark.bootui("rule:RAPI-RESP-006")
def test_rapi_resp_006_fires_on_204_with_a_content_capable_return() -> None:
    # ported: RestApiRuleAccuracyTests.responseRulesRespectExplicitDynamicAndImperativeStatusSelection
    # ported: RestApiRulesTests.responseEdgeRulesFlagStatusMismatches
    found = _findings(_no_content_body_app(), "RAPI-RESP-006")
    assert len(found) == 1
    _located(found[0], "GET", "/rule-accuracy/contradiction", "no_content_body")


@pytest.mark.bootui("rule:RAPI-RESP-006")
def test_rapi_resp_006_passes_an_empty_or_dynamic_204() -> None:
    # ported: RestApiRuleAccuracyTests.responseRulesRespectExplicitDynamicAndImperativeStatusSelection
    # ported: RestApiRulesTests.cleanControllerPassesNewerRules
    app = _app()

    @app.get("/rule-accuracy/no-content", status_code=204, summary="s", tags=["t"])
    def no_content_empty() -> None:
        return None

    @app.get("/rule-accuracy/dynamic-no-content", status_code=204, summary="s", tags=["t"])
    def dynamic_no_content() -> Response:
        return Response(status_code=204)

    assert _findings(app, "RAPI-RESP-006") == []


@pytest.mark.bootui("rule:RAPI-RESP-011")
def test_rapi_resp_011_fires_on_an_optional_get() -> None:
    # ported: RestApiContractDefectRulesTests.optionalReadsAreReportedUnlessTheApplicationOwnsTheStatus
    app = _app()

    @app.get("/items/{item_id}", summary="s", tags=["t"])
    def find(item_id: str) -> Optional[Payload]:  # noqa: UP045 - BootUI's Optional<Payload>
        return None

    @app.get("/other/{item_id}", summary="s", tags=["t"])
    def find_other(item_id: str) -> Payload | None:
        return None

    found = _findings(app, "RAPI-RESP-011")
    assert [f.severity for f in found] == ["LOW", "LOW"]
    _located(found[0], "GET", "/items/{item_id}", "find")
    _located(found[1], "GET", "/other/{item_id}", "find_other")


@pytest.mark.bootui("rule:RAPI-RESP-011")
def test_rapi_resp_011_passes_when_the_application_owns_the_status() -> None:
    # ported: RestApiContractDefectRulesTests.optionalReadsAreReportedUnlessTheApplicationOwnsTheStatus
    # #findEntity (ResponseEntity<Optional<...>>: dynamic) and #save (POST) are not reported
    app = _app()

    @app.get("/entities/{item_id}", summary="s", tags=["t"])
    def find_entity(item_id: str, response: Response) -> Payload | None:
        return None

    @app.post("/items", status_code=201, summary="s", tags=["t"])
    def save(body: Payload) -> Payload | None:
        return body

    assert _findings(app, "RAPI-RESP-011") == []


# --- DTO & payload contracts ----------------------------------------------------------------------------------------


@pytest.mark.bootui("rule:RAPI-DTO-001")
def test_rapi_dto_001_fires_on_a_persistence_class_response() -> None:
    # ported: RestApiRulesTests.payloadRulesFlagEntitiesAndCollections
    # ported: RestApiRuleAccuracyTests.payloadAndPaginationRulesDistinguishEntitiesBinaryAndExplicitStreams
    app = _app()

    @app.get("/rule-accuracy/entities", response_model=None, summary="s", tags=["t"])
    def entity_array(limit: int = 10) -> list[OrderEntity]:
        return []

    finding = _one(app, "RAPI-DTO-001", "HIGH")
    _located(finding, "GET", "/rule-accuracy/entities", "entity_array")
    assert "OrderEntity" in finding.message


@pytest.mark.bootui("rule:RAPI-DTO-001")
def test_rapi_dto_001_passes_a_dto_response() -> None:
    # ported: RestApiRulesTests.cleanControllerPassesCoreRules
    app = _app()

    @app.get("/api/v1/users/{user_id}", summary="s", tags=["t"])
    def get_user(user_id: str) -> Payload:
        return Payload(id=user_id, name="n")

    assert _findings(app, "RAPI-DTO-001") == []


# --- Pagination ----------------------------------------------------------------------------------------------------


@pytest.mark.bootui("rule:RAPI-PAGE-001")
def test_rapi_page_001_fires_on_an_unpaginated_collection_read() -> None:
    # ported: RestApiRulesTests.paginationRuleFlagsUnpaginatedCollectionRead
    # BadOrderController#getOrders: List<...> with no Pageable
    app = _app()

    @app.get("/orders", summary="s", tags=["t"])
    def list_orders() -> list[Payload]:
        return []

    finding = _one(app, "RAPI-PAGE-001", "LOW")
    _located(finding, "GET", "/orders", "list_orders")


@pytest.mark.bootui("rule:RAPI-PAGE-001")
def test_rapi_page_001_passes_binary_and_paginated_reads() -> None:
    # ported: RestApiRuleAccuracyTests.payloadAndPaginationRulesDistinguishEntitiesBinaryAndExplicitStreams
    # Responses#bytes (byte[]) is not among the four flagged handlers; a paged read is the clean analogue
    app = _app()

    @app.get("/rule-accuracy/bytes", response_model=None, summary="s", tags=["t"])
    def read_bytes() -> bytes:
        return b""

    @app.get("/api/v1/users", summary="s", tags=["t"])
    def list_users(page: int = 0, size: int = 20) -> list[Payload]:
        return []

    assert _findings(app, "RAPI-PAGE-001") == []


# --- Versioning ----------------------------------------------------------------------------------------------------


@pytest.mark.bootui("rule:RAPI-VER-001")
def test_rapi_ver_001_fires_on_inconsistent_versioning_ignoring_api_docs() -> None:
    # ported: RestApiContractDefectRulesTests.aLeadingV3SegmentIsAVersionNotDocumentation
    app = _app()

    @app.get("/v3/orders", summary="s", tags=["t"])
    def versioned(limit: int = 10) -> list[Payload]:
        return []

    @app.get("/orders", summary="s", tags=["t"])
    def unversioned(limit: int = 10) -> list[Payload]:
        return []

    @app.get("/v3/api-docs", summary="s", tags=["t"])
    def docs() -> Payload:
        return Payload(id="1", name="n")

    finding = _one(app, "RAPI-VER-001", "INFO")
    assert finding.target == "application"
    assert "1 of 2 API handler(s)" in finding.message
    assert ".unversioned" in finding.message
    assert ".docs" not in finding.message


@pytest.mark.bootui("rule:RAPI-VER-001")
def test_rapi_ver_001_fires_when_no_handler_is_versioned() -> None:
    # ported: RestApiRulesTests.versioningRulesFlagWildcardAndMissingVersion
    app = _app()

    @app.get("/orders", summary="s", tags=["t"])
    def list_orders(limit: int = 10) -> list[Payload]:
        return []

    finding = _one(app, "RAPI-VER-001", "INFO")
    assert finding.target == "application"


# Guard, not a port: BootUI has no case for a path with no fixed segment; it must stay an API handler.
def test_rapi_ver_001_counts_a_variable_only_path_as_an_api_handler() -> None:
    # BootUI isNonApiEndpoint: a path with no static segment is not operational or documentation, so it is an API
    # handler (regression guard for the api-docs fix, which reads static segments)
    app = _app()

    @app.get("/v1/orders", summary="s", tags=["t"])
    def list_orders(limit: int = 10) -> list[Payload]:
        return []

    @app.get("/{slug}", summary="s", tags=["t"])
    def by_slug(slug: str) -> Payload:
        return Payload(id=slug, name="n")

    finding = _one(app, "RAPI-VER-001", "INFO")
    assert "1 of 2 API handler(s)" in finding.message
    assert ".by_slug" in finding.message


@pytest.mark.bootui("rule:RAPI-VER-001")
def test_rapi_ver_001_passes_consistent_path_versioning() -> None:
    # ported: RestApiRulesTests.versioningRulesFlagWildcardAndMissingVersion
    app = _app()

    @app.get("/api/v1/users", summary="s", tags=["t"])
    def list_users(limit: int = 10) -> list[Payload]:
        return []

    @app.get("/api/v1/users/{user_id}", summary="s", tags=["t"])
    def get_user(user_id: str) -> Payload:
        return Payload(id=user_id, name="n")

    assert _findings(app, "RAPI-VER-001") == []


# --- Documentation -------------------------------------------------------------------------------------------------


@pytest.mark.bootui("rule:RAPI-DOC-001")
def test_rapi_doc_001_fires_on_an_undocumented_operation() -> None:
    # ported: RestApiRulesTests.documentationRulesAreSkippedWithoutSpringdocAndFireWithIt
    app = _app()

    @app.get("/api/v1/users", tags=["users"])
    def list_users(limit: int = 10) -> list[Payload]:
        return []

    finding = _one(app, "RAPI-DOC-001", "INFO")
    _located(finding, "GET", "/api/v1/users", "list_users")


@pytest.mark.bootui("rule:RAPI-DOC-001")
def test_rapi_doc_001_passes_a_summary_or_docstring() -> None:
    # ported: RestApiRuleAccuracyTests.documentationRecognizesTagContainersAndOperationTagsWithoutRequiringAnnotationsForGeneration  # noqa: E501
    app = _app()

    @app.get("/api/v1/users", summary="List users", tags=["users"])
    def list_users(limit: int = 10) -> list[Payload]:
        return []

    @app.get("/api/v1/users/{user_id}", tags=["users"])
    def get_user(user_id: str) -> Payload:
        """Read one user."""
        return Payload(id=user_id, name="n")

    assert _findings(app, "RAPI-DOC-001") == []


@pytest.mark.bootui("rule:RAPI-DOC-002")
def test_rapi_doc_002_fires_on_an_untagged_operation() -> None:
    # ported: RestApiRulesTests.documentationRulesAreSkippedWithoutSpringdocAndFireWithIt
    app = _app()

    @app.get("/api/v1/users", summary="List users")
    def list_users(limit: int = 10) -> list[Payload]:
        return []

    finding = _one(app, "RAPI-DOC-002", "INFO")
    _located(finding, "GET", "/api/v1/users", "list_users")


@pytest.mark.bootui("rule:RAPI-DOC-002")
def test_rapi_doc_002_passes_operation_tags() -> None:
    # ported: RestApiRuleAccuracyTests.documentationRecognizesTagContainersAndOperationTagsWithoutRequiringAnnotationsForGeneration  # noqa: E501
    app = _app()

    @app.get("/api/v1/users", summary="List users", tags=["users"])
    def list_users(limit: int = 10) -> list[Payload]:
        return []

    assert _findings(app, "RAPI-DOC-002") == []


# --- Error handling & documentation (ERR) --------------------------------------------------------------------------


@pytest.mark.bootui("rule:RAPI-ERR-001")
def test_rapi_err_001_fires_without_application_exception_handler() -> None:
    # ported: RestApiRulesTests.errorHandlingRulesReflectCentralizedHandling
    app = _app()

    @app.get("/items", summary="s", tags=["t"])
    def get_items() -> list[Payload]:
        return []

    finding = _one(app, "RAPI-ERR-001", "INFO")
    assert finding.target == "application"
    assert "No application-wide exception handler was registered" in finding.message


@pytest.mark.bootui("rule:RAPI-ERR-001")
def test_rapi_err_001_passes_with_application_exception_handler() -> None:
    # ported: RestApiRulesTests.errorHandlingRulesReflectCentralizedHandling
    app = _app()

    @app.get("/items", summary="s", tags=["t"])
    def get_items() -> list[Payload]:
        return []

    @app.exception_handler(Exception)
    async def handle_all(_request: object, _exc: Exception) -> Response:
        return Response(status_code=500)

    assert _findings(app, "RAPI-ERR-001") == []


@pytest.mark.bootui("rule:RAPI-ERR-004")
def test_rapi_err_004_fires_when_handler_renders_body_without_explicit_status() -> None:
    # ported: RestApiRulesTests.errorHandlingEdgeRuleFlagsBodyWithoutErrorStatus
    app = _app()

    @app.get("/items", summary="s", tags=["t"])
    def get_items() -> list[Payload]:
        return []

    @app.exception_handler(RuntimeError)
    def handle_runtime(_request: object, exc: RuntimeError) -> JSONResponse:
        return JSONResponse({"error": "runtime"})

    finding = _one(app, "RAPI-ERR-004", "MEDIUM")
    assert "handle_runtime" in finding.target
    assert "declares a body without explicit status selection" in finding.message


@pytest.mark.bootui("rule:RAPI-ERR-004")
def test_rapi_err_004_passes_when_explicit_status_is_declared() -> None:
    # ported: RestApiRulesTests.phase3ErrorHandlingRulesFlagAndPass
    app = _app()

    @app.get("/items", summary="s", tags=["t"])
    def get_items() -> list[Payload]:
        return []

    @app.exception_handler(RuntimeError)
    def handle_runtime(_request: object, exc: RuntimeError) -> JSONResponse:
        return JSONResponse({"error": "runtime"}, status_code=500)

    assert _findings(app, "RAPI-ERR-004") == []


@pytest.mark.bootui("rule:RAPI-ERR-005")
def test_rapi_err_005_fires_when_broad_handler_declares_fixed_non_5xx_status() -> None:
    # ported: RestApiRulesTests.broadExceptionHandlerRuleAllowsA500FallbackButFlagsANon5xxCollapse
    app = _app()

    @app.get("/items", summary="s", tags=["t"])
    def get_items() -> list[Payload]:
        return []

    @app.exception_handler(Exception)
    def handle_all(_request: object, exc: Exception) -> JSONResponse:
        return JSONResponse({"error": "bad request"}, status_code=400)

    finding = _one(app, "RAPI-ERR-005", "LOW")
    assert "handle_all" in finding.target
    assert "catches Exception/BaseException and maps it to a fixed non-5xx status (400)" in finding.message


@pytest.mark.bootui("rule:RAPI-ERR-005")
def test_rapi_err_005_passes_when_broad_handler_uses_500_or_specific_exception() -> None:
    # ported: RestApiRuleAccuracyTests.errorStatusReviewRequiresObservableFixedNonServerError
    app = _app()

    @app.get("/items", summary="s", tags=["t"])
    def get_items() -> list[Payload]:
        return []

    @app.exception_handler(Exception)
    def handle_all(_request: object, exc: Exception) -> JSONResponse:
        return JSONResponse({"error": "server error"}, status_code=500)

    @app.exception_handler(ValueError)
    def handle_val(_request: object, exc: ValueError) -> JSONResponse:
        return JSONResponse({"error": "not found"}, status_code=404)

    assert _findings(app, "RAPI-ERR-005") == []


@pytest.mark.bootui("rule:RAPI-ERR-007")
def test_rapi_err_007_fires_on_throttling_status_without_retry_after() -> None:
    # ported: RestApiRulesTests.retryAfterRuleFlagsThrottlingResponsesFromHandlersAndExceptionHandlers
    app = _app()

    @app.get("/rate-limited", status_code=429, summary="s", tags=["t"])
    def rate_limited() -> Payload:
        return Payload(id="1", name="slow down")

    @app.exception_handler(RuntimeError)
    def handle_unavailable(_request: object, exc: RuntimeError) -> JSONResponse:
        return JSONResponse({"error": "busy"}, status_code=503)

    found = _findings(app, "RAPI-ERR-007")
    assert len(found) == 2
    for f in found:
        assert f.severity == "INFO"
        assert "review Retry-After policy" in f.message


@pytest.mark.bootui("rule:RAPI-ERR-007")
def test_rapi_err_007_passes_on_non_throttling_responses() -> None:
    # ported: RestApiRulesTests.retryAfterRuleFlagsThrottlingResponsesFromHandlersAndExceptionHandlers
    app = _app()

    @app.get("/items", status_code=200, summary="s", tags=["t"])
    def get_items() -> list[Payload]:
        return []

    @app.exception_handler(RuntimeError)
    def handle_runtime(_request: object, exc: RuntimeError) -> JSONResponse:
        return JSONResponse({"error": "runtime"}, status_code=500)

    assert _findings(app, "RAPI-ERR-007") == []


@pytest.mark.bootui("rule:RAPI-ERR-008")
def test_rapi_err_008_fires_on_raw_string_error_body() -> None:
    # ported: RestApiRulesTests.headBodyAndRawStringExceptionRulesFireOnSpringAndJaxRs
    app = _app()

    @app.get("/items", summary="s", tags=["t"])
    def get_items() -> list[Payload]:
        return []

    @app.exception_handler(RuntimeError)
    def handle_runtime(_request: object, exc: RuntimeError) -> PlainTextResponse:
        return PlainTextResponse("error message", status_code=400)

    finding = _one(app, "RAPI-ERR-008", "LOW")
    assert "handle_runtime" in finding.target
    assert "returns a raw String error body" in finding.message


@pytest.mark.bootui("rule:RAPI-ERR-008")
def test_rapi_err_008_passes_on_structured_error_body() -> None:
    # ported: RestApiRulesTests.headBodyAndRawStringExceptionRulesFireOnSpringAndJaxRs
    app = _app()

    @app.get("/items", summary="s", tags=["t"])
    def get_items() -> list[Payload]:
        return []

    @app.exception_handler(RuntimeError)
    def handle_runtime(_request: object, exc: RuntimeError) -> JSONResponse:
        return JSONResponse({"error": "error message"}, status_code=400)

    assert _findings(app, "RAPI-ERR-008") == []


@pytest.mark.bootui("rule:RAPI-ERR-010")
def test_rapi_err_010_fires_on_differing_known_error_categories() -> None:
    # ported: RestApiRuleAccuracyTests.errorContractsCompareKnownShapesWithoutTreatingNegotiationAsAContradiction
    app = _app()

    @app.get("/items", summary="s", tags=["t"])
    def get_items() -> list[Payload]:
        return []

    @app.exception_handler(ValueError)
    def handle_problem(_request: object, exc: ValueError) -> JSONResponse:
        return JSONResponse({"type": "about:blank", "title": "bad", "status": 400}, status_code=400)

    @app.exception_handler(RuntimeError)
    def handle_text(_request: object, exc: RuntimeError) -> PlainTextResponse:
        return PlainTextResponse("error", status_code=500)

    finding = _one(app, "RAPI-ERR-010", "LOW")
    assert finding.target == "application"
    assert "different error body declaration categories:" in finding.message
    assert "problem details" in finding.message
    assert "raw string" in finding.message


@pytest.mark.bootui("rule:RAPI-ERR-010")
def test_rapi_err_010_passes_when_categories_align_or_dynamic() -> None:
    # ported: RestApiRuleAccuracyTests.errorContractsCompareKnownShapesWithoutTreatingNegotiationAsAContradiction
    app = _app()

    @app.get("/items", summary="s", tags=["t"])
    def get_items() -> list[Payload]:
        return []

    @app.exception_handler(ValueError)
    def handle_val(_request: object, exc: ValueError) -> JSONResponse:
        return JSONResponse({"type": "about:blank", "title": "bad", "status": 400}, status_code=400)

    @app.exception_handler(RuntimeError)
    def handle_run(_request: object, exc: RuntimeError) -> JSONResponse:
        return JSONResponse({"type": "about:blank", "title": "err", "status": 500}, status_code=500)

    assert _findings(app, "RAPI-ERR-010") == []


@pytest.mark.bootui("rule:RAPI-ERR-011")
def test_rapi_err_011_retired_definition_emits_no_findings() -> None:
    # ported: RestApiRuleRegistryTests.retiredDefinitionsKeepTheirIdsWithoutEmittingFindings
    app = _app()

    @app.get("/items", summary="s", tags=["t"])
    def get_items() -> list[Payload]:
        return []

    @app.exception_handler(RuntimeError)
    def handle_stack(_request: object, exc: RuntimeError) -> PlainTextResponse:
        return PlainTextResponse("traceback", status_code=500)

    assert _findings(app, "RAPI-ERR-011") == []


# --- Leak ----------------------------------------------------------------------------------------------------------

PLANTED = "sk_live_PLANTED_7f3a9c2e41b8d6"


def _leak_app(secret_segment: str) -> FastAPI:
    """A secret in every text a rest-api finding could draw from: the route path (findings name it, and NAME-003
    quotes the offending segment), and the docstring, summary, description, tag, default value and body example."""
    app = _app()

    @app.api_route(
        "/getOrders/{order_id}/",
        methods=["GET", "POST"],
        description=f"token={PLANTED}",
        response_model=None,
    )
    def create_order(
        order_id: str,
        token: str = PLANTED,
        body: Annotated[Any, Body(examples=[{"password": PLANTED}])] = None,
    ) -> list[OrderEntity]:
        return []

    @app.get(f"/v1/{secret_segment}/{{item_id}}", summary=f"password={PLANTED}", tags=[PLANTED])
    def delete_it(item_id: str) -> Payload | None:
        """Secret: api_key=sk_live_PLANTED_7f3a9c2e41b8d6."""
        return None

    return app


def _assert_locations_only(app: FastAPI) -> None:
    run = assess(FastApiIntrospector(app).api_model(), Masker(Exposure.MASKED, True))
    assert len({f.rule_id for f in run.findings}) >= 5  # the plant sits on routes that really produce findings
    assert any(f.rule_id == "RAPI-NAME-003" and ".delete_it" in f.message for f in run.findings)  # quotes the segment
    for finding in run.findings:
        assert PLANTED not in finding.target
        assert PLANTED not in finding.message
        assert PLANTED not in finding.fingerprint


def test_rest_api_findings_report_locations_only() -> None:
    # The secret is a whole path segment: masked in the target and in NAME-003's quoted segment.
    _assert_locations_only(_leak_app(PLANTED))
