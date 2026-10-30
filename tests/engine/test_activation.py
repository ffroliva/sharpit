"""Fail-closed activation decision (spec 7.3, contract 10).

Ported from BootUI ``BootUiActivationConditionTests`` and ``BootUiActivationConditionAdditionalTests``.
Mapping rules: ``bootui.<prop>`` -> ``SHARPIT_<PROP>``; Spring active profiles -> ``SHARPIT_PROFILES``/``APP_ENV``/
``ENVIRONMENT``; the DevTools classpath check -> the ``dev_signal`` parameter; Spring's fallback ``default`` profile ->
"no profile variable set" (sharpit has no fallback profile).

Dropped, no Python meaning:
- ``autoEnablesWhenDevtoolsIsPresent`` builds a ClassLoader with a compiled stub class; replaced by the dev_signal
  tests below. ``devtoolsClassNameConstantIsCorrect`` asserts a JVM class-name constant.
- ``yamlEnabledOnActivates`` / ``yamlEnabledOffDisables`` drive Spring's YamlPropertySourceLoader; the YAML-boolean
  spellings (true/yes -> ON, false/no -> OFF) are kept in ``test_enabled_spellings``.
"""

from __future__ import annotations

import pytest

from sharpit.engine.activation import ActivationStatus, active_profiles, decide
from sharpit.settings import SharpitSettings, load_settings

SIGNAL = "uvicorn --reload"


def run(environ: dict[str, str], kwargs: dict[str, object] | None = None, dev_signal: str | None = None):
    settings = load_settings(kwargs or {}, environ)
    return decide(settings, active_profiles(settings, environ), dev_signal)


# ---- BootUiActivationConditionTests --------------------------------------------------------------------------------


def test_auto_enables_on_enabled_profile():  # ported: BootUiActivationConditionTests.autoEnablesOnEnabledProfile
    a = run({"APP_ENV": "dev"})
    assert a.enabled is True
    assert a.reason == "Enabled by active profile 'dev'"


def test_auto_disables_without_enabled_profile_and_without_signal():
    # ported: BootUiActivationConditionTests.autoDisablesWithoutEnabledProfileAndWithoutDevtools
    a = run({"APP_ENV": "staging"})
    assert a.enabled is False
    assert a.reason == "Disabled: no enabled profile and no reloading development server detected"


def test_disabled_profile_forces_off_by_default():
    # ported: BootUiActivationConditionTests.disabledProfileForcesOffByDefault
    a = run({"SHARPIT_PROFILES": "prod,dev"})
    assert a.enabled is False
    assert a.reason == "Disabled because active profile 'prod' is in SHARPIT_DISABLED_PROFILES"


def test_enabled_on_overrides_disabled_profile_but_records_warning():
    # ported: BootUiActivationConditionTests.enabledOnOverridesDisabledProfileButRecordsWarning
    a = run({"APP_ENV": "prod", "SHARPIT_ENABLED": "ON"})
    assert a.enabled is True
    assert a.reason == "Explicitly enabled (SHARPIT_ENABLED=ON) despite disabled profile 'prod'"
    assert a.warnings == ("Profile 'prod' is in SHARPIT_DISABLED_PROFILES but SHARPIT_ENABLED=ON forces it on.",)


def test_enabled_off_forces_disabled():  # ported: BootUiActivationConditionTests.enabledOffForcesDisabled
    a = run({"APP_ENV": "dev", "SHARPIT_ENABLED": "OFF"})
    assert a.enabled is False
    assert a.reason == "Disabled by SHARPIT_ENABLED=OFF"


def test_invalid_enabled_mode_fails_closed_even_with_enabled_profile():
    # ported: BootUiActivationConditionTests.invalidEnabledModeFailsClosedEvenWithEnabledProfile
    a = run({"APP_ENV": "dev", "SHARPIT_ENABLED": "maybe"})
    assert a.enabled is False
    assert a.reason == "Disabled: invalid SHARPIT_ENABLED value 'maybe'"


def test_invalid_enabled_disables():  # also covers the dev-signal and disabled-profile precedence
    a = run({"SHARPIT_ENABLED": "maybe"}, dev_signal=SIGNAL)
    assert a.enabled is False
    assert a.reason == "Disabled: invalid SHARPIT_ENABLED value 'maybe'"
    assert run({"SHARPIT_ENABLED": "maybe", "APP_ENV": "prod"}).reason.startswith("Disabled: invalid")


def test_mode_is_case_insensitive():  # ported: BootUiActivationConditionTests.modeIsCaseInsensitive
    assert run({"SHARPIT_ENABLED": " on "}).enabled is True


def test_custom_enabled_profiles_are_honored():
    # ported: BootUiActivationConditionTests.customEnabledProfilesAreHonored
    a = run({"APP_ENV": "sandbox", "SHARPIT_ENABLED_PROFILES": "sandbox, testing"})
    assert a.enabled is True
    assert a.reason == "Enabled by active profile 'sandbox'"


def test_custom_disabled_profiles_are_honored():
    # ported: BootUiActivationConditionTests.customDisabledProfilesAreHonored
    a = run({"APP_ENV": "sandbox", "SHARPIT_DISABLED_PROFILES": "sandbox"})
    assert a.enabled is False
    assert "sandbox" in a.reason


def test_blank_enabled_profiles_falls_back_to_defaults():
    # ported: BootUiActivationConditionTests.blankEnabledProfilesPropertyFallsBackToDefaults
    a = run({"APP_ENV": "local", "SHARPIT_ENABLED_PROFILES": "   "})
    assert a.enabled is True
    assert "local" in a.reason


def test_auto_enables_when_dev_signal_present():
    # ported: BootUiActivationConditionTests.autoEnablesWhenDevtoolsIsPresent (DevTools classpath -> dev_signal)
    a = run({}, dev_signal=SIGNAL)
    assert a.enabled is True
    assert a.reason == "Enabled because a reloading development server was detected (uvicorn --reload)"


# ---- BootUiActivationConditionAdditionalTests ----------------------------------------------------------------------


def test_dev_signal_does_not_override_explicit_off():
    # ported: BootUiActivationConditionAdditionalTests.devtoolsDoesNotOverrideExplicitOff
    a = run({"SHARPIT_ENABLED": "OFF"}, dev_signal=SIGNAL)
    assert a.enabled is False
    assert "OFF" in a.reason


def test_dev_signal_is_overridden_by_disabled_profile():
    # ported: BootUiActivationConditionAdditionalTests.devtoolsIsOverriddenByDisabledProfile
    a = run({"APP_ENV": "prod"}, dev_signal=SIGNAL)
    assert a.enabled is False
    assert "prod" in a.reason


def test_dev_signal_plus_explicit_on_activates_even_with_disabled_profile():
    # ported: BootUiActivationConditionAdditionalTests.devtoolsPlusExplicitOnActivatesEvenWithDisabledProfile
    a = run({"APP_ENV": "prod", "SHARPIT_ENABLED": "ON"}, dev_signal=SIGNAL)
    assert a.enabled is True
    assert a.warnings


def test_no_signal_and_no_enabled_profile_is_disabled():
    # ported: BootUiActivationConditionAdditionalTests.devtoolsAbsentAndNoEnabledProfileIsDisabled
    # (Spring's fallback profile -> no profile variable set at all)
    a = run({})
    assert a.enabled is False
    assert "no enabled profile" in a.reason


def test_multiple_custom_disabled_profiles_first_match_disables():
    # ported: BootUiActivationConditionAdditionalTests.multipleCustomDisabledProfilesFirstMatchDisables
    a = run({"APP_ENV": "staging", "SHARPIT_DISABLED_PROFILES": "staging, uat, preprod"})
    assert a.enabled is False
    assert "staging" in a.reason


def test_non_matching_custom_disabled_profiles_do_not_disable():
    # ported: BootUiActivationConditionAdditionalTests.nonMatchingCustomDisabledProfilesDoesNotDisable
    assert run({"APP_ENV": "dev", "SHARPIT_DISABLED_PROFILES": "staging, uat"}).enabled is True


def test_default_production_profile_is_also_disabled():
    # ported: BootUiActivationConditionAdditionalTests.defaultProductionProfileIsAlsoDisabled
    a = run({"APP_ENV": "production"})
    assert a.enabled is False
    assert "production" in a.reason


def test_blank_disabled_profiles_falls_back_to_defaults():
    # ported: BootUiActivationConditionAdditionalTests.blankDisabledProfilesPropertyFallsBackToDefaults
    a = run({"APP_ENV": "prod", "SHARPIT_DISABLED_PROFILES": "   "})
    assert a.enabled is False
    assert "prod" in a.reason


def test_custom_disabled_profile_with_on_mode_records_warning_and_activates():
    # ported: BootUiActivationConditionAdditionalTests.customDisabledProfileWithOnModeRecordsWarningAndActivates
    a = run({"APP_ENV": "nightly", "SHARPIT_DISABLED_PROFILES": "nightly", "SHARPIT_ENABLED": "ON"})
    assert a.enabled is True
    assert any("nightly" in w for w in a.warnings)


@pytest.mark.parametrize(
    ("raw", "enabled", "reason_part"),
    [("YES", True, "ON"), ("TRUE", True, "ON"), ("FALSE", False, "OFF"), ("no", False, "OFF")],
)
def test_enabled_spellings(raw: str, enabled: bool, reason_part: str):
    # ported: BootUiActivationConditionAdditionalTests.yesValueActivatesAsYamlBooleanTrue / trueValueActivates... /
    # falseValueDisablesAsYamlBooleanFalse
    a = run({"APP_ENV": "dev", "SHARPIT_ENABLED": raw})
    assert a.enabled is enabled
    assert reason_part in a.reason


def test_numeric_enabled_value_fails_closed():
    # ported: BootUiActivationConditionAdditionalTests.numericEnabledValueFailsClosed
    assert run({"SHARPIT_ENABLED": "1"}).enabled is False


def test_invalid_enabled_reason_mentions_supplied_value():
    # ported: BootUiActivationConditionAdditionalTests.invalidEnabledValueReasonMentionsTheSuppliedValue
    assert "bogus" in run({"SHARPIT_ENABLED": "bogus"}).reason


def test_off_mode_with_no_profiles_disables():
    # ported: BootUiActivationConditionAdditionalTests.offModeWithNoProfilesDisables
    a = run({"SHARPIT_ENABLED": "OFF"})
    assert (a.enabled, a.reason) == (False, "Disabled by SHARPIT_ENABLED=OFF")


def test_on_mode_with_no_profiles_activates():
    # ported: BootUiActivationConditionAdditionalTests.onModeWithNoProfilesActivates
    a = run({"SHARPIT_ENABLED": "ON"})
    assert (a.enabled, a.reason) == (True, "Enabled by SHARPIT_ENABLED=ON")


# ---- sharpit additions ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("value", [" Production ", "PROD", "prod ", "\tProd"])
def test_disabled_profile_case_and_whitespace(value: str):
    a = run({"APP_ENV": value})
    assert a.enabled is False
    assert "is in SHARPIT_DISABLED_PROFILES" in a.reason


def test_disabled_profile_case_and_whitespace_in_a_list():
    assert run({"APP_ENV": " Dev , Production "}).enabled is False


def test_union_of_profile_vars():
    a = run({"APP_ENV": "dev", "ENVIRONMENT": "production"})
    assert a.enabled is False
    assert "production" in a.reason


def test_bare_ENV_ignored():
    # POSIX shells set ENV to a file path; it must never count as a profile, enabled or disabled.
    a = run({"ENV": "dev"})
    assert a.enabled is False
    assert run({"ENV": "prod", "APP_ENV": "dev"}).enabled is True


def test_active_profiles_union_order_lowercase_dedup():
    s = load_settings({}, {})
    env = {"SHARPIT_PROFILES": "Dev, local", "APP_ENV": "LOCAL,qa", "ENVIRONMENT": " "}
    assert active_profiles(s, env) == ["dev", "local", "qa"]


def test_active_profiles_custom_vars():
    s = load_settings({"profile_vars": ("MY_ENV",)}, {})
    assert active_profiles(s, {"MY_ENV": "x", "APP_ENV": "dev"}) == ["x"]


def test_empty_env_is_unset():
    a = run({"SHARPIT_ENABLED": ""}, {"enabled": "OFF"})
    assert a.reason == "Disabled by SHARPIT_ENABLED=OFF"


def test_env_overrides_kwargs():
    a = run({"SHARPIT_ENABLED": "OFF"}, {"enabled": "ON"})
    assert a.enabled is False


def test_kwargs_enabled_bool_and_on():
    assert run({}, {"enabled": "ON"}).enabled is True
    assert run({"APP_ENV": "dev"}, {"enabled": False}).enabled is False


def test_warnings_reach_activation():
    a = run({"APP_ENV": "dev", "SHARPIT_EXPOSE_VALUES": "full", "SHARPIT_READ_ONLY": "bad"})
    assert a.enabled is True
    assert a.warnings == (
        "Ignoring invalid SHARPIT_READ_ONLY value 'bad'",
        "SHARPIT_EXPOSE_VALUES=FULL exposes unmasked secrets",
    )


def test_settings_warnings_precede_decision_warnings():
    a = run({"APP_ENV": "prod", "SHARPIT_ENABLED": "ON", "SHARPIT_MASK_SECRETS": "zzz"})
    assert a.warnings[0] == "Ignoring invalid SHARPIT_MASK_SECRETS value 'zzz'"
    assert len(a.warnings) == 2


def test_localhost_only_follows_allow_non_localhost():
    assert run({"APP_ENV": "dev"}).localhost_only is True
    assert run({"APP_ENV": "dev", "SHARPIT_ALLOW_NON_LOCALHOST": "true"}).localhost_only is False


def test_to_dto_shape():
    a = ActivationStatus(enabled=True, localhost_only=True, reason="r", warnings=("w",))
    assert a.to_dto() == {"enabled": True, "localhostOnly": True, "reason": "r", "warnings": ["w"]}


def test_decide_accepts_unnormalised_profiles():
    assert decide(SharpitSettings(), [" PROD "], None).enabled is False
