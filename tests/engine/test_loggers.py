import logging
from collections.abc import Iterator
from typing import Any

import pytest

from conftest import SideEffectGuard, golden
from sharpit.engine.collectors.loggers import loggers_report, set_level
from sharpit.engine.paging import BadRequest

LEVELS = ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"]


@pytest.fixture
def restore_levels() -> Iterator[None]:
    """Put every logger level (and the root's) back, so a test that sets levels leaves no trace."""
    saved = {n: lg.level for n, lg in logging.root.manager.loggerDict.items() if isinstance(lg, logging.Logger)}
    root = logging.root.level
    yield
    for name, lg in logging.root.manager.loggerDict.items():
        if isinstance(lg, logging.Logger):
            lg.setLevel(saved.get(name, logging.NOTSET))
    logging.root.setLevel(root)


def _by_name(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["name"]: entry for entry in report["loggers"]}


def test_shape_matches_golden_keys(no_side_effects: SideEffectGuard):
    report, expected = loggers_report(None, None, None), golden("loggers")
    assert list(report) == list(expected)
    assert list(report["loggers"][0]) == list(expected["loggers"][0])
    assert list(report["page"]) == list(expected["page"])
    assert report["availableLevels"] == LEVELS


def test_root_named_ROOT(no_side_effects: SideEffectGuard):
    root = _by_name(loggers_report(None, None, None))["ROOT"]
    assert root == {
        "name": "ROOT",
        "configuredLevel": logging.getLevelName(logging.root.level),
        "effectiveLevel": logging.getLevelName(logging.root.level),
    }


def test_placeholders_skipped_and_listing_creates_no_logger(no_side_effects: SideEffectGuard):
    logging.getLogger("phx.mid.leaf")  # creates PlaceHolders for 'phx' and 'phx.mid'
    before = set(logging.root.manager.loggerDict)
    names = _by_name(loggers_report(None, None, None))
    assert "phx.mid.leaf" in names
    assert "phx" not in names and "phx.mid" not in names
    assert set(logging.root.manager.loggerDict) == before


# ported: LoggersServiceTests.reportFiltersHiddenLoggersSortsByNameAndPages
def test_filters_own_loggers_sorts_by_name_and_pages(no_side_effects: SideEffectGuard):
    for name in ("pg.com.Beta", "pg.com.Alpha", "pg.org.Thing", "sharpit.pgsecret"):
        logging.getLogger(name)
    report = loggers_report("PG.COM", 1, 1)
    assert [lg["name"] for lg in report["loggers"]] == ["pg.com.Beta"]
    assert report["page"]["matched"] == 2
    assert report["page"]["offset"] == 1 and report["page"]["returned"] == 1
    everything = loggers_report(None, None, None)
    assert [lg["name"] for lg in everything["loggers"]] == sorted(lg["name"] for lg in everything["loggers"])
    assert "sharpit.pgsecret" not in _by_name(everything) and "sharpit" not in _by_name(everything)
    assert everything["page"]["total"] == len(everything["loggers"])


# ported: LoggersServiceTests.setLevelDelegatesToProviderAndPassesLevelThrough
def test_set_level_applies_and_returns_dto(restore_levels: None):
    assert set_level("setl.demo", "debug") == {
        "name": "setl.demo",
        "configuredLevel": "DEBUG",
        "effectiveLevel": "DEBUG",
    }
    assert logging.getLogger("setl.demo").level == logging.DEBUG


# ported: LoggersServiceTests.setLevelPassesBlankLevelThroughForTheProviderToInterpretAsReset
@pytest.mark.parametrize("blank", [None, "", "  "])
def test_blank_level_resets_named_logger_to_inherit(restore_levels: None, blank: str | None):
    logging.getLogger("setl.reset").setLevel(logging.DEBUG)
    result = set_level("setl.reset", blank)
    assert result["configuredLevel"] is None
    assert result["effectiveLevel"] == logging.getLevelName(logging.root.getEffectiveLevel())
    assert logging.getLogger("setl.reset").level == logging.NOTSET


def test_post_root_lowercase_accepted(restore_levels: None):
    assert set_level("root", "ERROR")["name"] == "ROOT"
    assert logging.root.level == logging.ERROR
    assert set_level("ROOT", "INFO")["configuredLevel"] == "INFO"
    assert logging.root.level == logging.INFO


def test_reset_root_to_warning(restore_levels: None):
    logging.root.setLevel(logging.DEBUG)
    assert set_level("ROOT", None) == {"name": "ROOT", "configuredLevel": "WARNING", "effectiveLevel": "WARNING"}
    assert logging.root.level == logging.WARNING


def test_unknown_level_400(restore_levels: None):
    for bad in ("LOUD", "WARN", "FATAL", "10"):
        with pytest.raises(BadRequest) as exc:
            set_level("setl.demo", bad)
        assert str(exc.value) == f"Unknown level '{bad}'"


# ported: LoggersServiceTests.setLevelRejectsWriteBlockedLoggerBeforeTouchingProvider
@pytest.mark.parametrize("name", ["sharpit", "sharpit.engine", "sharpit.zz.deep"])
def test_own_logger_refused(restore_levels: None, name: str):
    before = logging.getLogger("sharpit").level
    with pytest.raises(BadRequest) as exc:
        set_level(name, "DEBUG")
    assert str(exc.value) == f"Refusing to change the level of sharpit's own logger '{name}'."
    assert logging.getLogger("sharpit").level == before
    assert name == "sharpit" or name not in logging.root.manager.loggerDict


def test_similar_prefix_is_not_own_logger(restore_levels: None):
    assert set_level("sharpitx", "INFO")["configuredLevel"] == "INFO"


def test_empty_name_rejected():
    with pytest.raises(BadRequest) as exc:
        set_level("", "DEBUG")
    assert str(exc.value) == "'name' must be provided"
