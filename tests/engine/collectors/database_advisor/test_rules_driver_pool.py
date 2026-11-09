"""Driver and pool rules DB-DRIVER-007/008, DB-POOL-001..004 and the facts they read (plan A-dbadv-1 Task 3)."""

from __future__ import annotations

from typing import Any

import pytest

from sharpit.engine.collectors.database_advisor import rules_driver_pool
from sharpit.engine.collectors.database_advisor.catalog import Outcome, Pool, Source, engine_facts

QUEUE = Pool("QueuePool", max_size=15, unbounded=False, recycle=-1, pre_ping=False)
PG_SERVER = {"max_connections": "100", "superuser_reserved_connections": "3", "reserved_connections": "0"}


def _source(
    dialect: str = "postgresql",
    *,
    driver: str = "psycopg",
    pool: Pool | None = QUEUE,
    server: dict[str, str] | None = None,
    url_keys: frozenset[str] = frozenset(),
    echo: bool = False,
) -> Source:
    catalog: dict[str, Any] = {"dialect": dialect, "tables": [], "tableCount": 0, "truncated": False,
                               "complete": True, "diagnostics": [], "server": dict(PG_SERVER if server is None
                                                                                   else server)}  # fmt: skip
    return Source("db", dialect, driver, "AVAILABLE", None, catalog, pool, url_keys, echo)


def _pool(**changes: Any) -> Pool:
    return Pool(**{**vars(QUEUE), **changes})


def _check(rule_id: str, source: Source) -> Outcome:
    rule = next(r for r in rules_driver_pool.RULES if r.definition.id == rule_id)
    return rule.check(source)


def _identities(outcome: Outcome) -> list[str] | str:
    return [identity for _target, _message, identity in outcome] if isinstance(outcome, list) else outcome


def test_engine_echo_is_reported() -> None:
    # ported: DatabaseAdvisorDriverSettingsRulesTests (a diagnostic setting that is on is one finding)
    assert _identities(_check("DB-DRIVER-007", _source(echo=True))) == ["ds=db|setting=echo"]


def test_engine_without_echo_passes() -> None:
    assert _identities(_check("DB-DRIVER-007", _source())) == []


def test_missing_connect_timeout_is_reported_for_libpq_style_drivers() -> None:
    # ported: DatabaseAdvisorDriverSettingsRulesTests (an absent timeout is reported, keyed by setting, not value)
    assert _identities(_check("DB-DRIVER-008", _source())) == ["ds=db|setting=connect_timeout"]


def test_configured_connect_timeout_passes() -> None:
    source = _source(url_keys=frozenset({"connect_timeout"}))

    assert _identities(_check("DB-DRIVER-008", source)) == []


def test_connect_timeout_rule_skips_drivers_with_their_own_default() -> None:
    outcomes = [
        _check("DB-DRIVER-008", _source(d, driver=v)) for d, v in (("mysql", "pymysql"), ("sqlite", "pysqlite"))
    ]

    assert [isinstance(o, str) for o in outcomes] == [True, True]


def test_idle_limit_fires_when_nothing_retires_or_pings_the_connection() -> None:
    # ported: DatabaseAdvisorPoolRulesTests.idleLimitFiresWhenNothingRetiresOrPingsTheConnectionBeforeTheServerCloses
    source = _source("mysql", driver="pymysql", server={"wait_timeout": "600", "max_connections": "151"})

    assert _identities(_check("DB-POOL-001", source)) == ["ds=db|pool=idle-limit"]


def test_idle_limit_fires_when_the_lifetime_is_not_shorter_than_the_server_limit() -> None:
    # ported: DatabaseAdvisorPoolRulesTests.idleLimitFiresWhenTheLifetimeIsNotShorterThanTheServerLimit
    source = _source("mysql", pool=_pool(recycle=600), server={"wait_timeout": "600", "max_connections": "151"})

    assert _identities(_check("DB-POOL-001", source)) == ["ds=db|pool=idle-limit"]


def test_idle_limit_is_covered_by_a_shorter_lifetime_or_pre_ping() -> None:
    # ported: DatabaseAdvisorPoolRulesTests.idleLimitIsCoveredByAShorterLifetimeAKeepaliveOrIdleRetirement
    server = {"wait_timeout": "600", "max_connections": "151"}
    outcomes = [_check("DB-POOL-001", _source("mysql", pool=p, server=server))
                for p in (_pool(recycle=300), _pool(pre_ping=True))]  # fmt: skip

    assert outcomes == [[], []]


def test_postgres_uses_idle_session_timeout_in_milliseconds_and_ignores_it_when_disabled() -> None:
    # ported: DatabaseAdvisorPoolRulesTests.postgresUsesIdleSessionTimeoutInItsUnitAndIgnoresItWhenDisabled
    fires = _source(server={**PG_SERVER, "idle_session_timeout": "60000"}, pool=_pool(recycle=120))
    disabled = _source(server={**PG_SERVER, "idle_session_timeout": "0"})

    assert _identities(_check("DB-POOL-001", fires)) == ["ds=db|pool=idle-limit"]
    assert _identities(_check("DB-POOL-001", disabled)) == []


def test_idle_limit_is_skipped_when_the_server_limit_is_unknown() -> None:
    # ported: DatabaseAdvisorPoolRulesTests.idleLimitIsSkippedWithTheSpecificReasonWhenThePoolOrServerIsUnknown
    outcome = _check("DB-POOL-001", _source("mysql", server={"max_connections": "151"}))

    assert isinstance(outcome, str)


def test_pool_rules_ignore_dialects_they_do_not_judge() -> None:
    # ported: DatabaseAdvisorPoolRulesTests.poolRulesIgnoreDialectsTheyDoNotJudge
    outcomes = [rule.check(_source("sqlite", driver="pysqlite", server={})) for rule in rules_driver_pool.RULES[2:]]

    assert [isinstance(o, str) for o in outcomes] == [True, True, True, True]


def test_a_pool_larger_than_the_usable_connections_fires_the_capacity_rule_and_not_the_share_rule() -> None:
    # ported: DatabaseAdvisorPoolRulesTests.aPoolLargerThanTheUsableConnectionsFiresTheCapacityRuleAndNotTheShareRule
    source = _source(pool=_pool(max_size=98))

    assert _identities(_check("DB-POOL-002", source)) == ["ds=db|pool=maximum-size"]
    assert _identities(_check("DB-POOL-004", source)) == []


def test_an_unbounded_overflow_exceeds_any_server_limit() -> None:
    source = _source(pool=_pool(max_size=None, unbounded=True))

    assert _identities(_check("DB-POOL-002", source)) == ["ds=db|pool=maximum-size"]


def test_a_pool_over_half_the_usable_connections_fires_the_share_heuristic() -> None:
    # ported: DatabaseAdvisorPoolRulesTests.aPoolOverHalfTheUsableConnectionsFiresTheShareHeuristicAtLowSeverity
    source = _source(pool=_pool(max_size=49))

    assert _identities(_check("DB-POOL-002", source)) == []
    assert _identities(_check("DB-POOL-004", source)) == ["ds=db|pool=maximum-size"]


def test_the_pool_share_boundary_uses_exact_integer_arithmetic() -> None:
    # ported: DatabaseAdvisorPoolRulesTests.thePoolShareBoundariesUseExactIntegerArithmetic (97 usable: 48 fits)
    assert _identities(_check("DB-POOL-004", _source(pool=_pool(max_size=48)))) == []


def test_the_capacity_rules_need_a_readable_server_limit() -> None:
    # ported: DatabaseAdvisorPoolRulesTests.theCapacityRulesNeedAReadablePoolSizeAndServerLimit
    source = _source(server={"max_connections": "100"})  # superuser_reserved_connections missing

    assert isinstance(_check("DB-POOL-002", source), str)


def test_an_unlimited_lifetime_is_reported_when_the_idle_limit_rule_does_not_own_the_datasource() -> None:
    # ported: DatabaseAdvisorPoolRulesTests.anUnlimitedLifetimeIsReportedWhenTheServerHasNoIdleLimitToCompareWith
    assert _identities(_check("DB-POOL-003", _source())) == ["ds=db|pool=max-lifetime"]


def test_an_unlimited_lifetime_is_not_reported_twice_when_the_idle_limit_rule_fires() -> None:
    # ported: DatabaseAdvisorPoolRulesTests.anUnlimitedLifetimeIsNotReportedTwiceWhenTheIdleLimitRuleFires
    source = _source("mysql", server={"wait_timeout": "600", "max_connections": "151"})

    assert _identities(_check("DB-POOL-003", source)) == []


def test_an_unlimited_lifetime_is_undecided_while_ownership_is_unsettled() -> None:
    # ported: DatabaseAdvisorPoolRulesTests.anUnlimitedLifetimeIsUndecidedWhileOwnershipByTheIdleLimitRuleIsUnsettled
    source = _source("mysql", server={"max_connections": "151"})

    assert isinstance(_check("DB-POOL-003", source), str)


def test_a_limited_lifetime_is_not_reported() -> None:
    # ported: DatabaseAdvisorPoolRulesTests.aLimitedLifetimeIsNotReported
    assert _identities(_check("DB-POOL-003", _source(pool=_pool(recycle=1800)))) == []


def test_password_never_read(monkeypatch: pytest.MonkeyPatch) -> None:
    # spec §5.8: the driver/pool facts never read url.password
    sa = pytest.importorskip("sqlalchemy")
    pytest.importorskip("psycopg")
    url_class = sa.engine.URL
    engine = sa.create_engine("postgresql+psycopg://app:s3cret-pw@localhost:5432/app?connect_timeout=3")
    reads: list[str] = []
    position = url_class._fields.index("password")
    monkeypatch.setattr(
        url_class, "password", property(lambda u: reads.append("password") or tuple.__getitem__(u, position))
    )

    facts = engine_facts(engine)

    assert reads == []
    assert facts[3] == frozenset({"connect_timeout"})


def test_query_string_values_are_never_kept() -> None:
    # spec §5.8: the allow-list keeps key names only; a secret's value is never read into the facts
    sa = pytest.importorskip("sqlalchemy")
    pytest.importorskip("psycopg")
    engine = sa.create_engine("postgresql+psycopg://app@localhost/app?password=qs-x1&sslpassword=qs-y2&token=qs-z3")

    facts = engine_facts(engine)

    assert "qs-" not in repr(facts)
    assert facts[3] == frozenset()
