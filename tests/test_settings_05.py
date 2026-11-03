"""0.5.0 settings for the committed lanes (spec §4.5): defaults, env override, fail-safe on an invalid value.

Names follow the settings rule (`bootui.mysql.max-sessions` -> `mysql_max_sessions`, env `SHARPIT_MYSQL_MAX_SESSIONS`).
MySQL bounds are BootUI's (WAVE-A §6, 1..2147483646); the database-advisor bounds are BootUI's fixed scan bounds
(WAVE-A §4: no ``bootui.database-advisor.*`` property, sharpit makes them settable); the architecture bounds are the
app-source index bounds (spec §4.2); ``app_package`` names the app package when it cannot be found (spec §4.2).
"""

from __future__ import annotations

import dataclasses

import pytest

from sharpit.settings import SharpitSettings, load_settings

# (name, default, env value, parsed, invalid env value)
SETTINGS_05: list[tuple[str, object, str, object, str]] = [
    ("mysql_max_sessions", 100, "7", 7, "0"),
    ("mysql_max_statements", 100, "7", 7, "-1"),
    ("mysql_max_indexes", 500, "7", 7, "2147483647"),
    ("mysql_max_tables", 200, "7", 7, "x"),
    ("mysql_max_lock_waits", 100, "7", 7, "0"),
    ("mysql_max_replication_channels", 10, "7", 7, "0"),
    ("mysql_max_settings", 40, "7", 7, "0"),
    ("database_advisor_max_tables", 300, "7", 7, "0"),
    ("database_advisor_max_columns", 300, "7", 7, "0"),
    ("database_advisor_max_indexes_per_table", 100, "7", 7, "0"),
    ("database_advisor_max_vendor_rows", 500, "7", 7, "0"),
    ("architecture_max_files", 2000, "7", 7, "0"),
    ("architecture_max_file_bytes", 524288, "7", 7, "0"),
    ("app_package", None, " myapp.web ", "myapp.web", "my-app/../x"),
]


@pytest.mark.parametrize(("name", "default", "raw", "parsed", "invalid"), SETTINGS_05, ids=[s[0] for s in SETTINGS_05])
def test_05_settings_defaults_and_env(name: str, default: object, raw: str, parsed: object, invalid: str) -> None:
    env = "SHARPIT_" + name.upper()

    assert name in {f.name for f in dataclasses.fields(SharpitSettings)}
    assert getattr(load_settings({}, {}), name) == default
    assert getattr(load_settings({}, {env: raw}), name) == parsed
    bad = load_settings({}, {env: invalid})
    assert getattr(bad, name) == default
    assert f"Ignoring invalid {env} value '{invalid}'" in bad.warnings
