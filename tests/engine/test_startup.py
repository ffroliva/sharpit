from __future__ import annotations

from conftest import SideEffectGuard
from sharpit.engine.collectors.startup import StartupTimeline
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

    assert timeline.report("startup", 1)["steps"][0]["name"] == "asgi.lifespan.startup"
    assert timeline.report()["steps"] == timeline.report("startup")["steps"]
    assert all(step["name"] != "sharpit.install" for step in timeline.report()["steps"])
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
