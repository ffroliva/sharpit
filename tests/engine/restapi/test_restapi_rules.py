"""REST API rules (port of BootUI ``RestApiRules`` heuristics for the 20 rules of spec §7.10, and the matching cases of
``RestApiRulesTests``). Routes are built as ``ApiRouteInfo`` directly: no FastAPI, no ``app.openapi()``."""

from collections.abc import Sequence
from typing import Annotated, Any, Optional

import pytest

from sharpit.engine.collectors.restapi.rules import scan, violations
from sharpit.engine.spi import ApiRouteInfo

APP_HANDLER = ("app.errors:on_error",)  # an application exception handler: ERR-001 passes


class Pet:
    pass


def route(
    path: str = "/v1/pets", methods: Sequence[str] = ("GET",), name: str = "read_pets", **kw: Any
) -> ApiRouteInfo:
    fields: dict[str, Any] = {
        "status_code": None,
        "response_model": None,
        "return_annotation": Pet,
        "dynamic_response": False,
        "has_body": False,
        "query_params": (),
        "summary": "Documented",
        "description": None,
        "tags": ("pets",),
        **kw,
    }
    return ApiRouteInfo(tuple(methods), path, f"app.pets:{name}", **fields)


def found(rule_id: str, routes: Sequence[ApiRouteInfo], handlers: Sequence[str] = APP_HANDLER) -> list[str]:
    return violations(routes, handlers)[rule_id]


class PetTable:
    __table__ = object()  # SQLModel table=True / SQLAlchemy declarative: duck-typed, never imported


class PetMapped:
    __mapper__ = object()


def test_clean_routes_pass_every_rule():
    # ported: RestApiRulesTests.cleanControllerPassesCoreRules
    routes = [
        route("/v1/pets", query_params=("limit", "offset"), response_model=list[Pet], return_annotation=list[Pet]),
        route("/v1/pets/{pet_id}", response_model=Pet, return_annotation=Pet, name="read_pet"),
        route("/v1/pets", ("POST",), "create_pet", status_code=201, has_body=True, response_model=Pet),
        route("/v1/pets/{pet_id}", ("DELETE",), "delete_pet", status_code=204, return_annotation=type(None)),
    ]
    assert {r.id: r.status for r in scan(routes, APP_HANDLER)} == dict.fromkeys(
        [r.id for r in scan([], APP_HANDLER)], "PASS"
    )


@pytest.mark.parametrize(
    ("rule_id", "bad", "good"),
    [
        # ported: routingRulesFlagBadController (no method constraint -> FastAPI: GET plus a mutating method)
        ("RAPI-MAP-001", route(methods=("GET", "POST")), route(methods=("GET",))),
        ("RAPI-MAP-003", route(name="delete_pet"), route(name="read_pet")),
        ("RAPI-MAP-003", route(name="createPet"), route(name="postprocess_pets")),  # stateChangingNameMatching...
        ("RAPI-MAP-005", route("/v1/pets/"), route("/v1/pets")),
        ("RAPI-MAP-005", route("/v1//pets"), route("/")),
        ("RAPI-MAP-007", route(methods=("DELETE",), has_body=True), route(methods=("PUT",), has_body=True)),
        ("RAPI-MAP-010", route("/v1/files/{rest:path}"), route("/v1/files/{name}")),
        ("RAPI-MAP-011", route("/v1/a/{a}/b/{b}/c/{c}/d/{d}"), route("/v1/a/{a}/b/{b}/c/{c}")),
        ("RAPI-NAME-001", route("/v1/getPets"), route("/v1/blog/post/{id}")),  # name001DoesNotFlagAmbiguousNoun...
        ("RAPI-NAME-001", route("/v1/create-pet", ("POST",)), route("/v1/pets")),
        (
            "RAPI-NAME-002",
            route("/v1/pet", return_annotation=list[Pet]),
            route("/v1/history", return_annotation=list[Pet]),
        ),
        ("RAPI-NAME-003", route("/v1/petTypes"), route("/v1/pet-types")),
        ("RAPI-NAME-003", route("/v1/pet_types"), route("/v1/pet-types/{pet_type}")),  # variables are not segments
        (
            "RAPI-RESP-001",
            route(methods=("POST",), name="create_pet"),
            route(methods=("POST",), name="create_pet", status_code=201),
        ),
        (
            "RAPI-RESP-001",
            route(methods=("POST",), name="add_pet"),
            route(methods=("POST",), name="add_pet", dynamic_response=True),
        ),
        (
            "RAPI-RESP-002",
            route(methods=("DELETE",), return_annotation=type(None)),
            route(methods=("DELETE",), status_code=204, return_annotation=type(None)),
        ),
        (
            "RAPI-RESP-002",
            route(methods=("DELETE",), return_annotation=None),
            route(methods=("DELETE",), response_model=Pet),
        ),
        (
            "RAPI-RESP-006",
            route(status_code=204, return_annotation=Pet),
            route(status_code=204, return_annotation=type(None)),
        ),
        (
            "RAPI-RESP-006",
            route(status_code=204, return_annotation=Pet, name="x"),
            route(status_code=204, dynamic_response=True, return_annotation=Pet),
        ),
        ("RAPI-DTO-001", route(response_model=PetTable), route(response_model=Pet)),
        ("RAPI-DTO-001", route(return_annotation=PetMapped), route(return_annotation=Pet)),
        ("RAPI-DTO-002", route(return_annotation=None), route(return_annotation=None, status_code=204)),
        ("RAPI-DTO-002", route(return_annotation=Any), route(return_annotation=Pet)),
        ("RAPI-DTO-002", route(return_annotation=dict), route(return_annotation=None, dynamic_response=True)),
        (
            "RAPI-PAGE-001",
            route(return_annotation=list[Pet]),
            route(return_annotation=list[Pet], query_params=("page",)),
        ),
        ("RAPI-PAGE-001", route(return_annotation=list[Pet]), route(return_annotation=list[Pet], methods=("POST",))),
        ("RAPI-DOC-001", route(summary=None), route(summary=None, description="From the docstring")),
        ("RAPI-DOC-002", route(tags=()), route(tags=("pets",))),
    ],
)
def test_rule_positive_and_negative(rule_id: str, bad: ApiRouteInfo, good: ApiRouteInfo):
    assert len(found(rule_id, [bad])) == 1, found(rule_id, [bad])
    assert found(rule_id, [good]) == []


def test_duplicate_route_mapping():
    # ported: routingRulesFlagBadController (MAP-002 message shape)
    first = route("/v1/pets", name="read_pets")
    second = route("/v1/pets", name="read_pets_again")
    assert found("RAPI-MAP-002", [first, second]) == [
        "GET /v1/pets with matching dispatch conditions handled by app.pets:read_pets, app.pets:read_pets_again"
    ]
    assert found("RAPI-MAP-002", [first, route("/v1/pets", ("POST",), "create_pet", status_code=201)]) == []


def test_name002_does_not_flag_uncountable_or_irregular():
    # ported: name002DoesNotFlagUncountableNouns
    for path in ("/v1/history", "/v1/people", "/v1/news", "/v1/data", "/v1/owners/{id}/pets"):
        assert found("RAPI-NAME-002", [route(path, return_annotation=list[Pet])]) == [], path
    assert found("RAPI-NAME-002", [route("/v1/pet", return_annotation=Pet)]) == []  # not a collection


def test_versioning_rules():
    # ported: versioningRulesFlagWildcardAndMissingVersion
    unversioned = [route("/pets"), route("/owners")]
    assert found("RAPI-VER-001", unversioned) == [
        "No API version signal (no /vN path, version header/param, or versioned media type) was detected across"
        " 2 handler(s)."
    ]
    mixed = [route("/v1/pets"), route("/owners"), route("/health")]  # /health is not an API path
    assert found("RAPI-VER-001", mixed) == [
        "Versioning is applied inconsistently: 1 of 2 API handler(s) have no version signal while others do."
        " Unversioned example(s): app.pets:read_pets [GET /owners]"
    ]
    assert found("RAPI-VER-001", [route("/v1/pets"), route("/V2/owners")]) == []
    assert found("RAPI-VER-001", [route("/health")]) == []


def test_error_handling_rule():
    # ported: errorHandlingRulesReflectCentralizedHandling
    defaults = (
        "fastapi.exception_handlers:http_exception_handler",
        "fastapi.exception_handlers:request_validation_exception_handler",
    )
    assert found("RAPI-ERR-001", [route()], defaults) == [
        "No application-wide exception handler was registered in app.exception_handlers for 1 route handler(s)."
    ]
    assert found("RAPI-ERR-001", [route()], (*defaults, "app.errors:on_error")) == []
    assert found("RAPI-ERR-001", [], defaults) == []  # nothing to handle


def test_generic_types_unwrapped():
    assert len(found("RAPI-DTO-001", [route(response_model=list[PetTable])])) == 1
    assert len(found("RAPI-DTO-001", [route(return_annotation=PetTable | None)])) == 1
    assert len(found("RAPI-DTO-001", [route(return_annotation=Optional[dict[str, list[PetMapped]]])])) == 1  # noqa: UP045
    assert len(found("RAPI-DTO-001", [route(return_annotation=Annotated[PetTable, "doc"])])) == 1
    owners = route("/v1/owners", response_model=list[Pet], return_annotation=list[Pet])
    assert found("RAPI-PAGE-001", [owners]) == [
        "app.pets:read_pets [GET /v1/owners] — collection response without limit/offset/page/cursor parameters"
    ]
    assert len(found("RAPI-PAGE-001", [route(return_annotation=Optional[list[Pet]])])) == 1  # noqa: UP045
    assert len(found("RAPI-PAGE-001", [route(return_annotation=tuple[Pet, ...] | None)])) == 1


def test_framework_routes_excluded():
    docs = ApiRouteInfo(("GET",), "/docs", "fastapi.applications:FastAPI.setup.<locals>.swagger_ui_html")
    own = ApiRouteInfo(("GET",), "/sharpit/api/x", "sharpit.fastapi.adapter:_routes.<locals>.x")
    starlette = ApiRouteInfo(("GET",), "/static", "starlette.staticfiles:StaticFiles")
    results = violations([docs, own, starlette], ())
    assert all(v == [] for v in results.values())


def test_samples_bounded_and_counts_full():
    routes = [route(f"/v1/getThing{i}", name=f"read_{i}") for i in range(15)]
    result = next(r for r in scan(routes, APP_HANDLER) if r.id == "RAPI-NAME-001")
    assert (result.status, result.violation_count, len(result.sample_violations)) == ("VIOLATION", 15, 10)


# --- lane D4: BootUI 2.2.0 rules (contract 0.4 drift §19) ------------------------------------------------------------

NEW_RULES_2_2_0 = ["RAPI-RESP-010", "RAPI-RESP-011", "RAPI-VALID-006", "RAPI-VER-007"]


@pytest.mark.parametrize("rule_id", NEW_RULES_2_2_0)
def test_rest_api_new_rules_fire(rule_id: str):
    # ported: RestApiRulesTests (2.2.0): RESP-011 is the one with a FastAPI analog; the other three read Spring
    # metadata FastAPI has no counterpart for and are registered as skipped, with a reason
    from sharpit.engine.collectors.restapi.rules import RULE_IDS, SKIPPED_RULES

    if rule_id != "RAPI-RESP-011":
        assert SKIPPED_RULES.get(rule_id, "").strip() != "", f"{rule_id} is registered as skipped with a reason"
        assert rule_id not in RULE_IDS
        return
    optional = route("/v1/pets/{id}", name="read_pet", return_annotation=Optional[Pet])  # noqa: UP045
    union = route("/v1/owners/{id}", name="read_owner", response_model=Pet | None)
    found_now = violations([optional, union], APP_HANDLER).get(rule_id, [])
    assert found_now == [
        "app.pets:read_pet [GET /v1/pets/{id}] — Optional return served as 200 with a null body",
        "app.pets:read_owner [GET /v1/owners/{id}] — Optional return served as 200 with a null body",
    ]
    quiet = [
        route("/v1/pets", name="read_pets"),  # not Optional
        route("/v1/a/{id}", name="read_a", return_annotation=Optional[Pet], status_code=202),  # noqa: UP045
        route("/v1/b/{id}", name="read_b", return_annotation=Optional[Pet], dynamic_response=True),  # noqa: UP045
        route("/v1/c/{id}", ("POST",), "make_c", return_annotation=Optional[Pet]),  # noqa: UP045
    ]
    assert violations(quiet, APP_HANDLER).get(rule_id, ["absent"]) == []
