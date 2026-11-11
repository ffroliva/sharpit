from __future__ import annotations

from typing import Any

from conftest import SideEffectGuard
from sharpit.engine.collectors.startup import StartupTimeline
from sharpit.engine.context import SharpitContext
from sharpit.engine.tools import CallContext, call_tool
from sharpit.engine.tools04.startup import COMMANDS, TOOLS
from sharpit.settings import load_settings


# ported: StartupControllerTests.startupHandlesZeroDurationWhenDurationIsNull
def test_startup_capacity_bounds_steps_and_emits_contract(no_side_effects: SideEffectGuard) -> None:
    timeline = StartupTimeline(1)
    timeline.record("asgi.lifespan.startup", None)
    timeline.record("ignored", 5)

    report = timeline.report()

    assert report == {
        "steps": [{"id": 0, "parentId": None, "name": "asgi.lifespan.startup", "durationMs": 0, "tags": []}]
    }
    no_side_effects.verify()


def test_startup_capacity_zero_disables(no_side_effects: SideEffectGuard) -> None:
    timeline = StartupTimeline(0)
    timeline.record("asgi.lifespan.startup", 1)

    assert timeline.report() == {"steps": []}
    no_side_effects.verify()


# ported: StartupControllerTests.startupReturnsEmptyWhenTimelineIsNull
def test_startup_empty_timeline_reports_empty(no_side_effects: SideEffectGuard) -> None:
    timeline = StartupTimeline(4096)

    assert timeline.report() == {"steps": []}
    no_side_effects.verify()


# ported: StartupControllerTests.startupFiltersBootUiStepsByDefault
def test_startup_query_and_limit_filter_steps(no_side_effects: SideEffectGuard) -> None:
    timeline = StartupTimeline(3)
    timeline.record("asgi.lifespan.startup", 2)
    timeline.record("sharpit.install", 1)

    assert [step["name"] for step in timeline.report()["steps"]] == ["asgi.lifespan.startup", "sharpit.install"]
    no_side_effects.verify()


def test_startup_settings_defaults_and_non_positive_capacity() -> None:
    defaults = load_settings({}, {})
    disabled_capacity = load_settings({"startup_capacity": 0}, {})
    negative_capacity = load_settings({"startup_capacity": -1}, {})

    assert defaults.startup_enabled is True
    assert defaults.startup_capacity == 4096
    assert disabled_capacity.startup_capacity == 0
    assert negative_capacity.startup_capacity == -1


def test_startup_invalid_capacity_fails_safe_and_warns() -> None:
    settings = load_settings({}, {"SHARPIT_STARTUP_CAPACITY": "invalid"})

    assert settings.startup_capacity == 4096
    assert "Ignoring invalid SHARPIT_STARTUP_CAPACITY value" in " ".join(settings.warnings)


def test_startup_enabled_environment_overrides_kwargs() -> None:
    settings = load_settings({"startup_enabled": True}, {"SHARPIT_STARTUP_ENABLED": "false"})

    assert settings.startup_enabled is False


def test_startup_panel_setting_is_accepted_and_environment_override_applies() -> None:
    refused = ""
    try:
        settings = load_settings({"panels": {"startup": {"enabled": False}}}, {"SHARPIT_PANELS_STARTUP_ENABLED": "1"})
    except ValueError as exc:  # an unknown panel id is refused: the red before the panel is implemented
        settings, refused = None, str(exc)

    assert settings is not None, refused
    assert settings.panels["startup"].enabled is True


def test_startup_tool_uses_bootui_name_default_and_cli_path() -> None:
    tool = TOOLS[0]

    assert tool.name == "get_startup_timeline"
    assert tool.default_limit == 25
    assert COMMANDS[tool.name] == "startup"


Record = tuple[str, int, list[tuple[str, str]]]


def _mcp(records: list[Record], **args: Any) -> dict[str, Any]:
    settings = load_settings({"config_scan": False}, {})
    ctx = SharpitContext(settings=settings, activation=None, introspector=None)  # type: ignore[arg-type]
    for name, duration, tags in records:
        ctx.startup.record(name, duration, tags)
    return call_tool(CallContext(ctx, {}), "get_startup_timeline", args, via="cli")


BEANS: list[Record] = [
    ("spring.context.refresh", 900, []),
    ("spring.beans.instantiate", 40, [("beanName", "orders")]),
    ("spring.beans.instantiate", 300, [("beanName", "db")]),
]


# ported: McpAgentViewsTests.startupListsTheSlowestMatchingStepsFirst
def test_startup_tool_lists_slowest_matching_steps_first_with_page() -> None:
    slowest = _mcp(BEANS, limit=2)

    assert [step["id"] for step in slowest["steps"]] == [0, 2]
    assert slowest["page"] == {"total": 3, "matched": 3, "offset": 0, "limit": 2, "returned": 2, "hasMore": True}
    assert set(slowest) == {"steps", "page"}


# ported: McpAgentViewsTests.startupListsTheSlowestMatchingStepsFirst
def test_startup_tool_query_matches_tag_values() -> None:
    bean = _mcp(BEANS, query="orders", limit=25)

    assert [step["id"] for step in bean["steps"]] == [1]


def test_startup_tool_query_drops_nonmatching_steps_and_limit_truncates() -> None:
    records: list[Record] = [("asgi.lifespan.startup", 5, []), ("warmup.cache", 9, []), ("warmup.pool", 7, [])]

    assert [s["name"] for s in _mcp(records, query="warmup", limit=25)["steps"]] == ["warmup.cache", "warmup.pool"]
    assert [s["name"] for s in _mcp(records, limit=1)["steps"]] == ["warmup.cache"]
    assert _mcp(records, query="nothing", limit=25)["steps"] == []


def test_startup_report_hands_out_fresh_step_dicts() -> None:
    timeline = StartupTimeline(4)
    timeline.record("asgi.lifespan.startup", 5)

    timeline.report()["steps"][0]["tags"].append({"key": "x", "value": "y"})

    assert timeline.report()["steps"][0]["tags"] == []
