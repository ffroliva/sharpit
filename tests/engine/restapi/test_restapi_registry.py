"""REST API rule registry: the ported rules and the skip list together cover every documented BootUI id (spec §7.10).

The id list is committed (``tests/fixtures/restapi/rest_api_check_ids.txt``, with its boot-ui source commit); this test
never reads the boot-ui repository.
"""

from pathlib import Path

from sharpit.engine.advisors.dismissals import owning_panel
from sharpit.engine.collectors.restapi.rules import RULES, SKIPPED_RULES

IDS_FILE = Path(__file__).parents[2] / "fixtures" / "restapi" / "rest_api_check_ids.txt"
PORTED = [
    "RAPI-MAP-001",
    "RAPI-MAP-002",
    "RAPI-MAP-003",
    "RAPI-MAP-005",
    "RAPI-MAP-007",
    "RAPI-MAP-010",
    "RAPI-MAP-011",
    "RAPI-NAME-001",
    "RAPI-NAME-002",
    "RAPI-NAME-003",
    "RAPI-RESP-001",
    "RAPI-RESP-002",
    "RAPI-RESP-006",
    "RAPI-DTO-001",
    "RAPI-DTO-002",
    "RAPI-PAGE-001",
    "RAPI-VER-001",
    "RAPI-ERR-001",
    "RAPI-DOC-001",
    "RAPI-DOC-002",
]


def _documented() -> list[str]:
    lines = IDS_FILE.read_text("utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def test_registry_covers_every_documented_id():
    documented = _documented()
    assert len(documented) == 56 and len(set(documented)) == 56
    assert "81d1476af6bccb2b70830d3f1b6ac72b737ae2e2" in IDS_FILE.read_text("utf-8")  # the source commit is recorded
    ported = [r.id for r in RULES]
    assert ported == PORTED  # exactly the 20 rules of spec §7.10, in BootUI order
    assert set(ported).isdisjoint(SKIPPED_RULES)
    assert set(ported) | set(SKIPPED_RULES) == set(documented)
    assert all(reason.strip() for reason in SKIPPED_RULES.values())


def test_severities_match_bootui_calibration():
    # ported: RestApiRules severities (BootUI calibration), unchanged for sharpit
    expected = {
        "RAPI-MAP-001": "MEDIUM",
        "RAPI-MAP-002": "HIGH",
        "RAPI-MAP-003": "LOW",
        "RAPI-MAP-005": "INFO",
        "RAPI-MAP-007": "MEDIUM",
        "RAPI-MAP-010": "INFO",
        "RAPI-MAP-011": "INFO",
        "RAPI-NAME-001": "INFO",
        "RAPI-NAME-002": "INFO",
        "RAPI-NAME-003": "INFO",
        "RAPI-RESP-001": "LOW",
        "RAPI-RESP-002": "LOW",
        "RAPI-RESP-006": "HIGH",
        "RAPI-DTO-001": "HIGH",
        "RAPI-DTO-002": "LOW",
        "RAPI-PAGE-001": "LOW",
        "RAPI-VER-001": "INFO",
        "RAPI-ERR-001": "INFO",
        "RAPI-DOC-001": "INFO",
        "RAPI-DOC-002": "INFO",
    }
    assert {r.id: r.severity for r in RULES} == expected


def test_rule_texts_are_framework_neutral():
    for rule in RULES:
        text = " ".join((rule.name, rule.description, rule.recommendation))
        assert all(
            word not in text for word in ("Spring", "@Request", "@Response", "@Get", "JAX-RS", "JPA", "BootUI")
        ), rule.id
        assert rule.learn_more_url.startswith("https://"), rule.id
        assert rule.category in {
            "Routing & HTTP method mapping",
            "Naming & resource design",
            "Status codes & responses",
            "DTO & payload contracts",
            "Pagination & collections",
            "Versioning & content negotiation",
            "Error handling & documentation",
        }, rule.id


def test_unregistered_rapi_id_has_no_owner():
    # T10 narrows the rest-api dismissal owner from the RAPI- shape to the registered ids
    assert owning_panel("RAPI-MAP-001") == "rest-api"
    assert owning_panel("RAPI-MAP-004") is None  # documented but not ported
    assert owning_panel("RAPI-NOPE-999") is None
