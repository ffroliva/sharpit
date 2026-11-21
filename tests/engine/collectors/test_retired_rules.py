from sharpit.engine.advisors.report import apply_dismissals
from sharpit.engine.collectors import database_advisor
from sharpit.engine.collectors.architecture import rules as architecture_rules


def test_retired_architecture_ids_are_not_registered() -> None:
    # ported: ArchitectureRuleRegistryTests.retiredRuleIdsAreNeverRegisteredAgain
    architecture_ids = {rule.id for rule in architecture_rules.RULES}
    architecture_retired = getattr(architecture_rules, "RETIRED_RULE_IDS", frozenset())

    assert "ARCH-CODE-004" not in architecture_ids
    assert "ARCH-CODE-018" not in architecture_ids
    assert architecture_retired == {"ARCH-CODE-004", "ARCH-CODE-018"}


def test_retired_database_ids_are_not_registered() -> None:
    database_ids = {rule.definition.id for rule in database_advisor.RULES}
    database_retired = getattr(database_advisor, "RETIRED_RULE_IDS", frozenset())

    assert "DB-POOL-004" not in database_ids
    assert "DB-SERVER-002" not in database_ids
    assert database_retired == {"DB-POOL-004", "DB-SERVER-002"}
    assert database_retired.isdisjoint(database_ids)


def test_stored_dismissal_of_reserved_rule_id_does_not_dismiss_another_rule() -> None:
    report = {
        "results": [
            {
                "id": "ARCH-CODE-001",
                "severity": "LOW",
                "status": "VIOLATION",
                "violationCount": 1,
                "sampleViolations": ["print()"],
                "dismissed": False,
            }
        ],
        "scan": {"violationsFound": 1},
        "violationsFound": 1,
        "severityCounts": [],
    }

    updated = apply_dismissals(report, {"ARCH-CODE-004"})

    assert updated["results"][0]["dismissed"] is False
    assert updated["violationsFound"] == 1
