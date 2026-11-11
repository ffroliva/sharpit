"""Settings loading: env over kwargs, fail-safe values for invalid input, path validation.

The ported activation cases live in ``tests/engine/test_activation.py``; this module covers the settings half of the
BootUI properties (``bootui.*`` -> ``SHARPIT_*``).
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from sharpit.engine.masking import Exposure
from sharpit.settings import _NEVER_ECHOED, PanelSettings, SharpitSettings, load_settings
from sharpit.settings_registry import JOURNAL_SOURCES


def test_defaults():
    s = load_settings({"state_dir": ".sharpit"}, {})
    assert s == SharpitSettings(state_dir=".sharpit", panels=s.panels)
    assert s.enabled == "AUTO"
    assert s.enabled_profiles == ("dev", "local", "development")
    assert s.disabled_profiles == ("prod", "production")
    assert s.profile_vars == ("SHARPIT_PROFILES", "APP_ENV", "ENVIRONMENT")
    assert (s.path, s.api_path) == ("/sharpit", "/sharpit/api")
    assert s.expose_values is Exposure.MASKED
    assert s.warnings == ()
    assert (s.cli_max_results, s.cli_max_concurrent_calls, s.cli_execution_timeout) == (200, 20, 30.0)
    assert s.panels["mcp-server"] == PanelSettings(enabled=True, read_only=False)


def test_gateway_trust_default_off():
    assert load_settings({}, {}).trust_container_gateway == "OFF"


def test_env_overrides_kwargs():
    s = load_settings({"enabled": "ON", "read_only": False}, {"SHARPIT_ENABLED": "OFF", "SHARPIT_READ_ONLY": "yes"})
    assert s.enabled == "OFF"
    assert s.read_only is True


def test_empty_env_is_unset():
    s = load_settings({"path": "/dev"}, {"SHARPIT_PATH": "", "SHARPIT_ENABLED": "   "})
    assert s.path == "/dev"
    assert s.enabled == "AUTO"


def test_kwargs_used_when_env_absent():
    s = load_settings({"enabled_profiles": ["Qa", " stage "], "mcp_max_results": 5}, {})
    assert s.enabled_profiles == ("qa", "stage")
    assert s.mcp_max_results == 5


def test_unknown_kwarg_rejected():
    with pytest.raises(TypeError, match="enabled_profile"):
        load_settings({"enabled_profile": ["dev"]}, {})


@pytest.mark.parametrize("raw", ["true", "TRUE", "Yes", "on", "1"])
def test_boolean_truthy_spellings(raw: str):
    assert load_settings({}, {"SHARPIT_READ_ONLY": raw}).read_only is True


@pytest.mark.parametrize("raw", ["false", "No", "OFF", "0"])
def test_boolean_falsy_spellings(raw: str):
    assert load_settings({"read_only": True}, {"SHARPIT_READ_ONLY": raw}).read_only is False


@pytest.mark.parametrize(
    ("raw", "expected"), [("30", 30.0), ("30s", 30.0), ("1500ms", 1.5), ("2.5", 2.5), (" 10S ", 10.0)]
)
def test_duration_spellings(raw: str, expected: float):
    assert load_settings({}, {"SHARPIT_MCP_EXECUTION_TIMEOUT": raw}).mcp_execution_timeout == expected


def test_lists_comma_split_and_blank_items_dropped():
    s = load_settings({}, {"SHARPIT_ALLOWED_HOSTS": "a.test, b.test,,", "SHARPIT_TRUSTED_PROXIES": "10.0.0.0/8"})
    assert s.allowed_hosts == ("a.test", "b.test")
    assert s.trusted_proxies == ("10.0.0.0/8",)


def test_blank_profile_lists_fall_back_to_defaults():
    # ported: BootUiActivationConditionTests.blankEnabledProfilesPropertyFallsBackToDefaults
    s = load_settings({}, {"SHARPIT_ENABLED_PROFILES": " , ", "SHARPIT_DISABLED_PROFILES": ","})
    assert s.enabled_profiles == ("dev", "local", "development")
    assert s.disabled_profiles == ("prod", "production")


def test_config_scan_bool_or_list():
    assert load_settings({}, {"SHARPIT_CONFIG_SCAN": "false"}).config_scan is False
    assert load_settings({}, {"SHARPIT_CONFIG_SCAN": "app,lib"}).config_scan == ("app", "lib")
    assert load_settings({}, {}).config_scan is True


def test_panels_env_with_dash_id():
    s = load_settings({}, {"SHARPIT_PANELS_MCP_SERVER_ENABLED": "false", "SHARPIT_PANELS_LOGGERS_READ_ONLY": "true"})
    assert s.panels["mcp-server"] == PanelSettings(enabled=False, read_only=False)
    assert s.panels["loggers"] == PanelSettings(enabled=True, read_only=True)
    assert s.panels["config"] == PanelSettings()


def test_panels_kwargs_merge_with_env_per_field():
    s = load_settings(
        {"panels": {"loggers": {"read_only": True}, "beans": PanelSettings(enabled=False)}},
        {"SHARPIT_PANELS_LOGGERS_ENABLED": "false"},
    )
    assert s.panels["loggers"] == PanelSettings(enabled=False, read_only=True)
    assert s.panels["beans"] == PanelSettings(enabled=False)


def test_invalid_panel_flags_fail_safe():
    s = load_settings({}, {"SHARPIT_PANELS_MCP_SERVER_ENABLED": "maybe", "SHARPIT_PANELS_LOGGERS_READ_ONLY": "x"})
    assert s.panels["mcp-server"].enabled is False
    assert s.panels["loggers"].read_only is True
    assert "Ignoring invalid SHARPIT_PANELS_MCP_SERVER_ENABLED value 'maybe'" in s.warnings


# (field, env name, invalid raw, fail-safe value)
FAIL_SAFE: list[tuple[str, str, str, Any]] = [
    ("enabled", "SHARPIT_ENABLED", "maybe", "maybe"),  # stored raw; decide() turns it into "disabled"
    ("read_only", "SHARPIT_READ_ONLY", "perhaps", True),
    ("expose_values", "SHARPIT_EXPOSE_VALUES", "everything", Exposure.MASKED),
    ("mask_secrets", "SHARPIT_MASK_SECRETS", "nope", True),
    ("mcp_enabled", "SHARPIT_MCP_ENABLED", "sure", "OFF"),
    ("cli_enabled", "SHARPIT_CLI_ENABLED", "dunno", False),
    ("allow_non_localhost", "SHARPIT_ALLOW_NON_LOCALHOST", "2", False),
    ("trust_container_gateway", "SHARPIT_TRUST_CONTAINER_GATEWAY", "all", "OFF"),
    ("show_banner", "SHARPIT_SHOW_BANNER", "later", True),
    ("vulnerabilities_osv_enabled", "SHARPIT_VULNERABILITIES_OSV_ENABLED", "?", False),
    ("vulnerabilities_epss_enabled", "SHARPIT_VULNERABILITIES_EPSS_ENABLED", "?", False),
    ("vulnerabilities_max_packages", "SHARPIT_VULNERABILITIES_MAX_PACKAGES", "many", 500),
    ("vulnerabilities_max_advisories", "SHARPIT_VULNERABILITIES_MAX_ADVISORIES", "-3", 200),
    ("vulnerabilities_request_timeout", "SHARPIT_VULNERABILITIES_REQUEST_TIMEOUT", "soon", 10.0),
    ("mcp_max_results", "SHARPIT_MCP_MAX_RESULTS", "0", 200),
    ("mcp_max_payload_bytes", "SHARPIT_MCP_MAX_PAYLOAD_BYTES", "big", 1048576),
    ("mcp_max_concurrent_calls", "SHARPIT_MCP_MAX_CONCURRENT_CALLS", "1.5", 20),
    ("mcp_execution_timeout", "SHARPIT_MCP_EXECUTION_TIMEOUT", "5m", 30.0),
    ("mcp_max_response_bytes", "SHARPIT_MCP_MAX_RESPONSE_BYTES", "huge", 4194304),
    ("cli_max_results", "SHARPIT_CLI_MAX_RESULTS", "lots", 200),
    ("cli_max_concurrent_calls", "SHARPIT_CLI_MAX_CONCURRENT_CALLS", "-1", 20),
    ("cli_execution_timeout", "SHARPIT_CLI_EXECUTION_TIMEOUT", "xs", 30.0),
]


@pytest.mark.parametrize(("field", "env", "raw", "expected"), FAIL_SAFE, ids=[f[0] for f in FAIL_SAFE])
def test_invalid_values_fail_safe(field: str, env: str, raw: str, expected: Any):
    s = load_settings({}, {env: raw})
    assert getattr(s, field) == expected
    assert f"Ignoring invalid {env} value '{raw}'" in s.warnings


def test_invalid_env_beats_a_good_kwarg_with_the_fail_safe():
    s = load_settings(
        {"read_only": False, "mask_secrets": False}, {"SHARPIT_READ_ONLY": "x", "SHARPIT_MASK_SECRETS": "x"}
    )
    assert s.read_only is True
    assert s.mask_secrets is True


def test_expose_full_warns():
    s = load_settings({}, {"SHARPIT_EXPOSE_VALUES": "full"})
    assert s.expose_values is Exposure.FULL
    assert s.warnings == ("SHARPIT_EXPOSE_VALUES=FULL exposes unmasked secrets",)


def test_expose_metadata_only_no_warning():
    s = load_settings({}, {"SHARPIT_EXPOSE_VALUES": "metadata_only"})
    assert s.expose_values is Exposure.METADATA_ONLY
    assert s.warnings == ()


def test_session_dirs_isolated_in_tests():
    import os
    import tempfile
    from pathlib import Path

    for name in ("SHARPIT_COPILOT_SESSION_STATE_DIR", "SHARPIT_CLAUDE_CODE_SESSION_STATE_DIR"):
        path = Path(os.environ.get(name, ""))
        assert path.is_relative_to(tempfile.gettempdir())
        assert not path.exists() or not list(path.iterdir())


def test_path_must_start_with_slash():
    with pytest.raises(ValueError, match="path"):
        load_settings({"path": "sharpit"}, {})


@pytest.mark.parametrize("path", ["/", "/sharpit/"])
@pytest.mark.parametrize("route", ["kwarg", "env"])
def test_path_rejects_root_and_trailing_slash(path: str, route: str):
    # "/" would mount over the whole host app (even inactive); a trailing slash yields "/sharpit//api"
    kwargs, environ = ({"path": path}, {}) if route == "kwarg" else ({}, {"SHARPIT_PATH": path})
    with pytest.raises(ValueError, match="path must not"):
        load_settings(kwargs, environ)


def test_install_refuses_root_path():
    from starlette.applications import Starlette

    import sharpit

    with pytest.raises(ValueError, match="path must not"):
        sharpit.install(Starlette(), path="/")


def test_api_path_derives_from_path():
    s = load_settings({}, {"SHARPIT_PATH": "/dev-console"})
    assert s.api_path == "/dev-console/api"


@pytest.mark.parametrize(
    ("path", "api_path", "ok"),
    [
        ("/sharpit", "/sharpit/api", True),
        ("/sharpit", "/sharpit/x/api", True),
        ("/sharpit", "/sharpitized/api", False),
        ("/sharpit", "/api", False),
        ("/sharpit", "/sharpit", False),
        ("/sharpit", "/sharpit/", False),
        ("/sharpit", "/sharpit//api", False),
    ],
)
def test_api_path_segment_boundary(path: str, api_path: str, ok: bool):
    if ok:
        assert load_settings({"path": path, "api_path": api_path}, {}).api_path == api_path
    else:
        with pytest.raises(ValueError, match="api_path"):
            load_settings({"path": path, "api_path": api_path}, {})


# BootUI property -> (dataclass field, a valid non-default sample). The env name is "SHARPIT_" + the property without
# "bootui.", with "." and "-" turned into "_", upper case.
PROPERTIES = {
    "bootui.enabled": ("enabled", "ON"),
    "bootui.enabled-profiles": ("enabled_profiles", "x,y"),
    "bootui.disabled-profiles": ("disabled_profiles", "x,y"),
    "bootui.profile-vars": ("profile_vars", "A,B"),
    "bootui.path": ("path", "/p"),
    "bootui.api-path": ("api_path", "/sharpit/p/api"),
    "bootui.allow-non-localhost": ("allow_non_localhost", "true"),
    "bootui.allowed-hosts": ("allowed_hosts", "h.test"),
    "bootui.trusted-proxies": ("trusted_proxies", "10.0.0.0/8"),
    "bootui.trust-container-gateway": ("trust_container_gateway", "AUTO"),
    "bootui.authentication.token": ("authentication_token", "tok"),
    "bootui.identity-key": ("identity_key", "a-shared-key-of-thirty-two-bytes"),  # sharpit-only: SQLite's opaque ids
    "bootui.read-only": ("read_only", "true"),
    "bootui.expose-values": ("expose_values", "METADATA_ONLY"),
    "bootui.mask-secrets": ("mask_secrets", "false"),
    "bootui.show-banner": ("show_banner", "false"),
    "bootui.free-on-idle.enabled": ("free_on_idle_enabled", "false"),
    "bootui.free-on-idle.timeout": ("free_on_idle_timeout", "45s"),
    "bootui.state-dir": ("state_dir", ".x"),
    "bootui.config-scan": ("config_scan", "false"),
    "bootui.vulnerabilities.osv-enabled": ("vulnerabilities_osv_enabled", "false"),
    "bootui.vulnerabilities.request-timeout": ("vulnerabilities_request_timeout", "3s"),
    "bootui.vulnerabilities.max-packages": ("vulnerabilities_max_packages", "7"),
    "bootui.vulnerabilities.max-advisories": ("vulnerabilities_max_advisories", "8"),
    "bootui.vulnerabilities.osv-base-uri": ("vulnerabilities_osv_base_uri", "http://osv.test"),
    "bootui.vulnerabilities.epss-enabled": ("vulnerabilities_epss_enabled", "false"),
    "bootui.vulnerabilities.epss-base-uri": ("vulnerabilities_epss_base_uri", "http://epss.test"),
    "bootui.mcp.enabled": ("mcp_enabled", "ON"),
    "bootui.mcp.max-results": ("mcp_max_results", "9"),
    "bootui.mcp.max-payload-bytes": ("mcp_max_payload_bytes", "10"),
    "bootui.mcp.max-concurrent-calls": ("mcp_max_concurrent_calls", "11"),
    "bootui.mcp.execution-timeout": ("mcp_execution_timeout", "12s"),
    "bootui.mcp.max-response-bytes": ("mcp_max_response_bytes", "13"),
    "bootui.cli.enabled": ("cli_enabled", "false"),
    "bootui.cli.max-results": ("cli_max_results", "14"),
    "bootui.cli.max-concurrent-calls": ("cli_max_concurrent_calls", "15"),
    "bootui.cli.execution-timeout": ("cli_execution_timeout", "16s"),
    # 0.2.0 (spec §12)
    "bootui.http-exchanges.max-exchanges": ("http_exchanges_max_exchanges", "17"),
    "bootui.exceptions.max-groups": ("exceptions_max_groups", "18"),
    "bootui.exceptions.max-occurrences-per-group": ("exceptions_max_occurrences_per_group", "19"),
    "bootui.exceptions.max-stack-frames": ("exceptions_max_stack_frames", "20"),
    "bootui.sql-trace.enabled": ("sql_trace_enabled", "false"),
    "bootui.sql-trace.sqlite3-enabled": ("sql_trace_sqlite3_enabled", "false"),  # sharpit-only: no BootUI property
    "bootui.sql-trace.recording": ("sql_trace_recording", "false"),
    "bootui.sql-trace.capture-parameters": ("sql_trace_capture_parameters", "true"),
    "bootui.sql-trace.capture-call-site": ("sql_trace_capture_call_site", "false"),
    "bootui.sql-trace.max-entries": ("sql_trace_max_entries", "21"),
    "bootui.sql-trace.slow-query-threshold-millis": ("sql_trace_slow_query_threshold_millis", "22"),
    "bootui.sql-trace.max-sql-length": ("sql_trace_max_sql_length", "23"),
    "bootui.sql-trace.max-parameter-length": ("sql_trace_max_parameter_length", "24"),
    "bootui.sql-trace.n-plus-one-threshold": ("sql_trace_n_plus_one_threshold", "25"),
    "bootui.activity.max-entries": ("activity_max_entries", "26"),
    "bootui.activity.request-slow-threshold-ms": ("activity_request_slow_threshold_ms", "27"),
    "bootui.activity.n-plus-one-threshold": ("activity_n_plus_one_threshold", "28"),
    "bootui.log-tail.max-lines": ("log_tail_max_lines", "29"),
    "bootui.log-tail.max-bytes": ("log_tail_max_bytes", "30"),
    "bootui.alembic.config": ("alembic_config", "db/alembic.ini"),
    "bootui.alembic.timeout": ("alembic_timeout", "31s"),
    "bootui.health.timeout": ("health_timeout", "32s"),
    "bootui.threads.max-stack-frames": ("threads_max_stack_frames", "33"),
    "bootui.advisors.max-retained-violations": ("advisors_max_retained_violations", "34"),
    "bootui.stream.max-seconds": ("stream_max_seconds", "35s"),
    "bootui.runtime-journal.enabled": ("runtime_journal_enabled", "false"),
    "bootui.runtime-journal.max-events": ("runtime_journal_max_events", "38"),
    "bootui.runtime-journal.max-bytes": ("runtime_journal_max_bytes", "39KB"),
    "bootui.runtime-journal.queue-capacity": ("runtime_journal_queue_capacity", "40"),
    "bootui.runtime-journal.sources": ("runtime_journal_sources", "SQL,http"),
    # 0.4.0 fields pre-created by lane F
    "bootui.activity.unbounded-read-factor": ("activity_unbounded_read_factor", "36"),
    "bootui.security-logs.max-logs": ("security_logs_max_logs", "37"),
    "bootui.postgresql.max-sessions": ("postgresql_max_sessions", "38"),
    "bootui.postgresql.max-statements": ("postgresql_max_statements", "39"),
    "bootui.postgresql.max-indexes": ("postgresql_max_indexes", "40"),
    "bootui.postgresql.max-tables": ("postgresql_max_tables", "41"),
    "bootui.postgresql.max-vacuum-tables": ("postgresql_max_vacuum_tables", "42"),
    "bootui.postgresql.max-replicas": ("postgresql_max_replicas", "43"),
    "bootui.postgresql.max-settings": ("postgresql_max_settings", "44"),
    "bootui.transactions.enabled": ("transactions_enabled", "false"),
    "bootui.transactions.recording": ("transactions_recording", "false"),
    "bootui.transactions.max-entries": ("transactions_max_entries", "45"),
    "bootui.transactions.slow-transaction-threshold-millis": ("transactions_slow_transaction_threshold_millis", "46"),
    "bootui.transactions.connection-hold-threshold-millis": ("transactions_connection_hold_threshold_millis", "47"),
    # 0.5.0 (spec §4.5; F5a-harness): BootUI's bootui.mysql.*, plus sharpit-only bounds under the same naming rule
    "bootui.mysql.max-sessions": ("mysql_max_sessions", "47"),
    "bootui.mysql.max-statements": ("mysql_max_statements", "47"),
    "bootui.mysql.max-indexes": ("mysql_max_indexes", "47"),
    "bootui.mysql.max-tables": ("mysql_max_tables", "47"),
    "bootui.mysql.max-lock-waits": ("mysql_max_lock_waits", "47"),
    "bootui.mysql.max-replication-channels": ("mysql_max_replication_channels", "47"),
    "bootui.mysql.max-settings": ("mysql_max_settings", "47"),
    "bootui.database-advisor.max-tables": ("database_advisor_max_tables", "47"),
    "bootui.database-advisor.max-columns": ("database_advisor_max_columns", "47"),
    "bootui.database-advisor.max-indexes-per-table": ("database_advisor_max_indexes_per_table", "47"),
    "bootui.database-advisor.max-vendor-rows": ("database_advisor_max_vendor_rows", "47"),
    "bootui.architecture.max-files": ("architecture_max_files", "47"),
    "bootui.architecture.max-file-bytes": ("architecture_max_file_bytes", "47"),
    "bootui.startup.enabled": ("startup_enabled", "false"),
    "bootui.startup.capacity": ("startup_capacity", "17"),
    "bootui.app-package": ("app_package", "myapp"),
}

NEW_DEFAULTS_0_2_0: dict[str, Any] = {
    "http_exchanges_max_exchanges": 200,
    "exceptions_max_groups": 100,
    "exceptions_max_occurrences_per_group": 25,
    "exceptions_max_stack_frames": 50,
    "sql_trace_enabled": True,
    "sql_trace_sqlite3_enabled": True,
    "sql_trace_recording": True,
    "sql_trace_capture_parameters": False,
    "sql_trace_capture_call_site": True,
    "sql_trace_max_entries": 200,
    "sql_trace_slow_query_threshold_millis": 100,
    "sql_trace_max_sql_length": 2000,
    "sql_trace_max_parameter_length": 200,
    "sql_trace_n_plus_one_threshold": 5,
    "activity_max_entries": 200,
    "activity_request_slow_threshold_ms": 1000,
    "activity_n_plus_one_threshold": 5,
    "log_tail_max_lines": 500,
    "log_tail_max_bytes": 1048576,
    "alembic_config": "alembic.ini",
    "alembic_timeout": 5.0,
    "health_timeout": 5.0,
    "threads_max_stack_frames": 64,
    "advisors_max_retained_violations": 10000,
    "stream_max_seconds": 3.0,
}


def test_new_settings_defaults():
    s = load_settings({}, {})
    assert {name: getattr(s, name) for name in NEW_DEFAULTS_0_2_0} == NEW_DEFAULTS_0_2_0
    assert s.warnings == ()


def test_w7_ai_settings_defaults():
    s = load_settings({}, {})
    assert getattr(s, "ai_token_series_minutes", None) == 60
    assert getattr(s, "ai_max_recent_chats", None) == 100
    assert getattr(s, "ai_show_content_capture_banner", None) is True


def test_w7_ai_settings_env_values():
    s = load_settings(
        {},
        {
            "SHARPIT_AI_TOKEN_SERIES_MINUTES": "24",
            "SHARPIT_AI_MAX_RECENT_CHATS": "12",
            "SHARPIT_AI_SHOW_CONTENT_CAPTURE_BANNER": "false",
        },
    )
    assert getattr(s, "ai_token_series_minutes", None) == 24
    assert getattr(s, "ai_max_recent_chats", None) == 12
    assert getattr(s, "ai_show_content_capture_banner", None) is False


@pytest.mark.parametrize(
    ("field", "env", "raw", "expected"),
    [
        ("ai_token_series_minutes", "SHARPIT_AI_TOKEN_SERIES_MINUTES", "many", 60),
        ("ai_max_recent_chats", "SHARPIT_AI_MAX_RECENT_CHATS", "many", 100),
        ("ai_show_content_capture_banner", "SHARPIT_AI_SHOW_CONTENT_CAPTURE_BANNER", "maybe", True),
    ],
)
def test_w7_ai_settings_invalid_values_fail_safe(field: str, env: str, raw: str, expected: Any):
    s = load_settings({}, {env: raw})
    assert getattr(s, field, None) == expected
    assert f"Ignoring invalid {env} value '{raw}'" in s.warnings


def test_new_settings_env_names():
    # every spec §12 env var is in the env-name table, so test_env_name_table checks its spelling and parsing
    covered = {field for field, _ in PROPERTIES.values()}
    assert set(NEW_DEFAULTS_0_2_0) <= covered


# spec §12 fail-safe column: (field, env name, invalid raw, fail-safe value)
NEW_FAIL_SAFE: list[tuple[str, str, str, Any]] = [
    ("http_exchanges_max_exchanges", "SHARPIT_HTTP_EXCHANGES_MAX_EXCHANGES", "lots", 200),
    ("exceptions_max_groups", "SHARPIT_EXCEPTIONS_MAX_GROUPS", "0", 100),
    ("exceptions_max_occurrences_per_group", "SHARPIT_EXCEPTIONS_MAX_OCCURRENCES_PER_GROUP", "-1", 25),
    ("exceptions_max_stack_frames", "SHARPIT_EXCEPTIONS_MAX_STACK_FRAMES", "x", 50),
    ("sql_trace_enabled", "SHARPIT_SQL_TRACE_ENABLED", "maybe", False),
    ("sql_trace_sqlite3_enabled", "SHARPIT_SQL_TRACE_SQLITE3_ENABLED", "maybe", False),
    ("sql_trace_recording", "SHARPIT_SQL_TRACE_RECORDING", "maybe", False),
    ("sql_trace_capture_parameters", "SHARPIT_SQL_TRACE_CAPTURE_PARAMETERS", "maybe", False),
    ("sql_trace_capture_call_site", "SHARPIT_SQL_TRACE_CAPTURE_CALL_SITE", "maybe", True),
    ("sql_trace_max_entries", "SHARPIT_SQL_TRACE_MAX_ENTRIES", "many", 200),
    ("sql_trace_slow_query_threshold_millis", "SHARPIT_SQL_TRACE_SLOW_QUERY_THRESHOLD_MILLIS", "-5", 100),
    ("sql_trace_max_sql_length", "SHARPIT_SQL_TRACE_MAX_SQL_LENGTH", "long", 2000),
    ("sql_trace_max_parameter_length", "SHARPIT_SQL_TRACE_MAX_PARAMETER_LENGTH", "0", 200),
    ("sql_trace_n_plus_one_threshold", "SHARPIT_SQL_TRACE_N_PLUS_ONE_THRESHOLD", "x", 5),
    ("activity_max_entries", "SHARPIT_ACTIVITY_MAX_ENTRIES", "x", 200),
    ("activity_request_slow_threshold_ms", "SHARPIT_ACTIVITY_REQUEST_SLOW_THRESHOLD_MS", "slow", 1000),
    ("activity_n_plus_one_threshold", "SHARPIT_ACTIVITY_N_PLUS_ONE_THRESHOLD", "-2", 5),
    ("log_tail_max_lines", "SHARPIT_LOG_TAIL_MAX_LINES", "x", 500),
    ("log_tail_max_bytes", "SHARPIT_LOG_TAIL_MAX_BYTES", "x", 1048576),
    ("alembic_timeout", "SHARPIT_ALEMBIC_TIMEOUT", "soon", 5.0),
    ("health_timeout", "SHARPIT_HEALTH_TIMEOUT", "0s", 5.0),
    ("threads_max_stack_frames", "SHARPIT_THREADS_MAX_STACK_FRAMES", "x", 64),
    ("advisors_max_retained_violations", "SHARPIT_ADVISORS_MAX_RETAINED_VIOLATIONS", "x", 10000),
    ("stream_max_seconds", "SHARPIT_STREAM_MAX_SECONDS", "forever", 3.0),
    ("runtime_journal_enabled", "SHARPIT_RUNTIME_JOURNAL_ENABLED", "maybe", False),
    ("runtime_journal_max_events", "SHARPIT_RUNTIME_JOURNAL_MAX_EVENTS", "0", 50_000),
    ("runtime_journal_max_bytes", "SHARPIT_RUNTIME_JOURNAL_MAX_BYTES", "lots", 32 * 1024 * 1024),
    ("runtime_journal_queue_capacity", "SHARPIT_RUNTIME_JOURNAL_QUEUE_CAPACITY", "-1", 10_000),
    ("runtime_journal_sources", "SHARPIT_RUNTIME_JOURNAL_SOURCES", "sql,nope", JOURNAL_SOURCES),
]


@pytest.mark.parametrize(("field", "env", "raw", "expected"), NEW_FAIL_SAFE, ids=[f[0] for f in NEW_FAIL_SAFE])
def test_new_settings_fail_safe(field: str, env: str, raw: str, expected: Any):
    s = load_settings({}, {env: raw})
    assert getattr(s, field) == expected
    assert f"Ignoring invalid {env} value '{raw}'" in s.warnings


def test_invalid_sql_trace_enabled_kwarg_fails_safe_even_over_default():
    s = load_settings({"sql_trace_enabled": "maybe"}, {})
    assert s.sql_trace_enabled is False


def test_alembic_config_fail_safe_is_unset():
    # spec §12: an unusable ini path is "unset" (no Alembic panel), not the default "alembic.ini"
    s = load_settings({"alembic_config": 5}, {})
    assert s.alembic_config is None
    assert "Ignoring invalid SHARPIT_ALEMBIC_CONFIG value '5'" in s.warnings


def test_zero_threshold_allowed():
    s = load_settings({}, {"SHARPIT_SQL_TRACE_SLOW_QUERY_THRESHOLD_MILLIS": "0"})
    assert (s.sql_trace_slow_query_threshold_millis, s.warnings) == (0, ())


@pytest.mark.parametrize("field", ["sql_trace_n_plus_one_threshold", "activity_n_plus_one_threshold"])
@pytest.mark.parametrize(("raw", "expected"), [("0", 2), ("1", 2), ("2", 2), ("7", 7)])
def test_n_plus_one_min_two(field: str, raw: str, expected: int):
    s = load_settings({}, {"SHARPIT_" + field.upper(): raw})
    assert (getattr(s, field), s.warnings) == (expected, ())


def test_log_tail_max_bytes_zero_rejected():
    s = load_settings({"log_tail_max_bytes": 0}, {})
    assert s.log_tail_max_bytes == 1048576
    assert "Ignoring invalid SHARPIT_LOG_TAIL_MAX_BYTES value '0'" in s.warnings


def test_new_panel_env_flags():
    s = load_settings({}, {"SHARPIT_PANELS_SQL_TRACE_READ_ONLY": "true", "SHARPIT_PANELS_HTTP_PROBE_ENABLED": "no"})
    assert s.panels["sql-trace"] == PanelSettings(enabled=True, read_only=True)
    assert s.panels["http-probe"] == PanelSettings(enabled=False, read_only=False)
    assert s.panels["database-connection-pools"] == PanelSettings()


def test_alembic_config_env_overrides_kwarg():
    assert load_settings({"alembic_config": "a.ini"}, {}).alembic_config == "a.ini"
    s = load_settings({"alembic_config": "a.ini"}, {"SHARPIT_ALEMBIC_CONFIG": " b.ini "})
    assert (s.alembic_config, s.warnings) == ("b.ini", ())
    assert load_settings({"alembic_config": "a.ini"}, {"SHARPIT_ALEMBIC_CONFIG": ""}).alembic_config == "a.ini"


def _env_name(prop: str) -> str:
    return "SHARPIT_" + prop.removeprefix("bootui.").replace(".", "_").replace("-", "_").upper()


def test_a_same_character_key_warns_without_showing_it() -> None:
    key = "k" * 32
    settings = load_settings({}, {"SHARPIT_IDENTITY_KEY": key})
    assert settings.identity_key == key
    assert settings.warnings == ("SHARPIT_IDENTITY_KEY is one character repeated: a weak key",)


def test_a_varied_key_does_not_warn() -> None:
    settings = load_settings({}, {"SHARPIT_IDENTITY_KEY": "a-shared-key-of-thirty-two-bytes"})
    assert settings.warnings == ()


@pytest.mark.parametrize("prop", PROPERTIES)
def test_env_name_table(prop: str):
    field, sample = PROPERTIES[prop]
    assert field == _env_name(prop).removeprefix("SHARPIT_").lower()
    default = getattr(load_settings({}, {}), field)
    s = load_settings({}, {_env_name(prop): sample})
    assert getattr(s, field) != default
    assert not any(w.startswith("Ignoring invalid") for w in s.warnings)


def test_env_name_table_covers_every_field():
    covered = {field for field, _ in PROPERTIES.values()}
    assert covered == {f.name for f in dataclasses.fields(SharpitSettings)} - {"panels", "warnings"}


# --- Task P1 item 6: misconfiguration is visible ------------------------------------------------------------------


def test_unknown_kwarg_suggests_the_closest_setting():
    with pytest.raises(TypeError, match=r"enabled_profile \(did you mean 'enabled_profiles'\?\)"):
        load_settings({"enabled_profile": ["dev"]}, {})
    with pytest.raises(TypeError, match=r"^Unknown sharpit setting\(s\): zzz$"):
        load_settings({"zzz": 1}, {})


@pytest.mark.parametrize(
    ("raw", "mode"),
    [("1", "ON"), ("0", "OFF"), ("on", "ON"), ("Yes", "ON"), ("TRUE", "ON"), ("off", "OFF"), ("No", "OFF")],
)
def test_enabled_accepts_one_and_zero_and_any_case(raw: str, mode: str):
    s = load_settings({}, {"SHARPIT_ENABLED": raw})
    assert (s.enabled, s.warnings) == (mode, ())


def test_api_path_error_names_the_actual_path():
    with pytest.raises(ValueError, match=r"'/elsewhere/api'"):
        load_settings({"api_path": "/elsewhere/api"}, {})


def test_invalid_token_warning_never_echoes_the_value():
    # install() now logs these warnings; an unusable token must not reach the log
    s = load_settings({"authentication_token": b"bytes-secret-value"}, {})
    assert s.authentication_token is None
    assert s.warnings == ("Ignoring invalid SHARPIT_AUTHENTICATION_TOKEN value",)


def test_panel_flag_none_fails_safe():
    # code review #10: None (or blank) must not fail open; read_only=None means read-only
    s = load_settings({"panels": {"loggers": {"read_only": None}, "beans": {"enabled": None, "read_only": " "}}}, {})
    assert s.panels["loggers"] == PanelSettings(enabled=True, read_only=True)
    assert s.panels["beans"] == PanelSettings(enabled=False, read_only=True)


def test_unknown_panel_id_rejected():
    with pytest.raises(ValueError, match=r"Unknown sharpit panel\(s\): nope.*known panels: overview"):
        load_settings({"panels": {"nope": {"enabled": False}}}, {})


def test_unknown_panel_flag_rejected():
    # a typo like "readonly" must not silently leave the panel writable
    match = r"Unknown flag\(s\) for sharpit panel config: readonly; known flags: enabled, read_only"
    with pytest.raises(ValueError, match=match):
        load_settings({"panels": {"config": {"readonly": True}}}, {})


@pytest.mark.parametrize("empty", [(), []])
def test_explicit_empty_list_kwarg_clears_the_default(empty: tuple[str, ...] | list[str]):
    # code review #14: only a blank env/string value falls back; an explicit empty sequence means "none"
    s = load_settings({"enabled_profiles": empty, "profile_vars": empty}, {})
    assert (s.enabled_profiles, s.profile_vars) == ((), ())


def test_settings_split_preserves_flat_kwargs_env_precedence_and_failsafe():
    import importlib.util

    assert importlib.util.find_spec("sharpit.settings_registry") is not None, (
        "settings families need an aggregated registry"
    )

    from sharpit.settings import _SPECS
    from sharpit.settings_registry import SPECS as registry_specs

    registered = set(registry_specs)
    fields = {f.name for f in dataclasses.fields(SharpitSettings)}
    assert registry_specs is _SPECS
    assert registered == set(_SPECS)
    assert fields - registered == {"panels", "warnings", "path", "api_path"}

    settings = load_settings(
        {"vulnerabilities_max_packages": 3, "mysql_max_sessions": 15, "authentication_token": "kw-token"},
        {
            "SHARPIT_VULNERABILITIES_MAX_PACKAGES": "7",
            "SHARPIT_MYSQL_MAX_SESSIONS": "0",
            "SHARPIT_AUTHENTICATION_TOKEN": "env-token",
        },
    )
    assert settings.vulnerabilities_max_packages == 7
    assert settings.mysql_max_sessions == 100
    assert settings.authentication_token == "env-token"
    assert "vulnerabilities_max_packages" in registered


@pytest.mark.parametrize(
    "field",
    sorted(_NEVER_ECHOED),
)
def test_invalid_sensitive_settings_never_echo_for_any_family(field: str):
    class Canary:
        def __str__(self) -> str:
            return "sensitive-warning-canary"

    raw = Canary()
    assert field in _NEVER_ECHOED
    settings = load_settings({field: raw}, {})
    assert settings.warnings
    assert all(str(raw) not in warning for warning in settings.warnings)


def test_credential_like_settings_are_registered_as_never_echoed():
    import sharpit.settings_registry as registry

    classify = getattr(registry, "unclassified_settings_fields", lambda _: {"classifier is missing"})

    assert not classify(SharpitSettings)


def test_new_unclassified_settings_field_is_reported():
    import sharpit.settings_registry as registry

    classify = getattr(
        registry, "unclassified_settings_fields", lambda settings: {f.name for f in dataclasses.fields(settings)}
    )
    extended = dataclasses.make_dataclass(
        "ExtendedSettings", [("future_secret", str, None)], bases=(SharpitSettings,), frozen=True
    )

    assert classify(extended) == {"future_secret"}


def test_invalid_settings_warning_order_matches_pre_split_registry():
    from sharpit.settings import _SPECS

    settings = load_settings({}, {f"SHARPIT_{name.upper()}": "zz-bad" for name in _SPECS})
    expected = [
        "ENABLED",
        "ALLOW_NON_LOCALHOST",
        "TRUST_CONTAINER_GATEWAY",
        "IDENTITY_KEY",
        "READ_ONLY",
        "EXPOSE_VALUES",
        "MASK_SECRETS",
        "SHOW_BANNER",
        "FREE_ON_IDLE_ENABLED",
        "FREE_ON_IDLE_TIMEOUT",
        "VULNERABILITIES_OSV_ENABLED",
        "VULNERABILITIES_REQUEST_TIMEOUT",
        "VULNERABILITIES_MAX_PACKAGES",
        "VULNERABILITIES_MAX_ADVISORIES",
        "VULNERABILITIES_OSV_BASE_URI",
        "VULNERABILITIES_EPSS_ENABLED",
        "VULNERABILITIES_EPSS_BASE_URI",
        "MCP_ENABLED",
        "MCP_MAX_RESULTS",
        "MCP_MAX_PAYLOAD_BYTES",
        "MCP_MAX_CONCURRENT_CALLS",
        "MCP_EXECUTION_TIMEOUT",
        "MCP_MAX_RESPONSE_BYTES",
        "CLI_ENABLED",
        "CLI_MAX_RESULTS",
        "CLI_MAX_CONCURRENT_CALLS",
        "CLI_EXECUTION_TIMEOUT",
        "HTTP_EXCHANGES_MAX_EXCHANGES",
        "EXCEPTIONS_MAX_GROUPS",
        "EXCEPTIONS_MAX_OCCURRENCES_PER_GROUP",
        "EXCEPTIONS_MAX_STACK_FRAMES",
        "SQL_TRACE_ENABLED",
        "SQL_TRACE_SQLITE3_ENABLED",
        "SQL_TRACE_RECORDING",
        "SQL_TRACE_CAPTURE_PARAMETERS",
        "SQL_TRACE_CAPTURE_CALL_SITE",
        "SQL_TRACE_MAX_ENTRIES",
        "SQL_TRACE_SLOW_QUERY_THRESHOLD_MILLIS",
        "SQL_TRACE_MAX_SQL_LENGTH",
        "SQL_TRACE_MAX_PARAMETER_LENGTH",
        "SQL_TRACE_N_PLUS_ONE_THRESHOLD",
        "ACTIVITY_MAX_ENTRIES",
        "ACTIVITY_REQUEST_SLOW_THRESHOLD_MS",
        "ACTIVITY_N_PLUS_ONE_THRESHOLD",
        "ACTIVITY_UNBOUNDED_READ_FACTOR",
        "LOG_TAIL_MAX_LINES",
        "LOG_TAIL_MAX_BYTES",
        "ALEMBIC_TIMEOUT",
        "HEALTH_TIMEOUT",
        "THREADS_MAX_STACK_FRAMES",
        "ADVISORS_MAX_RETAINED_VIOLATIONS",
        "STREAM_MAX_SECONDS",
        "RUNTIME_JOURNAL_ENABLED",
        "RUNTIME_JOURNAL_MAX_EVENTS",
        "RUNTIME_JOURNAL_MAX_BYTES",
        "RUNTIME_JOURNAL_QUEUE_CAPACITY",
        "RUNTIME_JOURNAL_SOURCES",
        "SECURITY_LOGS_MAX_LOGS",
        "POSTGRESQL_MAX_SESSIONS",
        "POSTGRESQL_MAX_STATEMENTS",
        "POSTGRESQL_MAX_INDEXES",
        "POSTGRESQL_MAX_TABLES",
        "POSTGRESQL_MAX_VACUUM_TABLES",
        "POSTGRESQL_MAX_REPLICAS",
        "POSTGRESQL_MAX_SETTINGS",
        "TRANSACTIONS_ENABLED",
        "TRANSACTIONS_RECORDING",
        "TRANSACTIONS_MAX_ENTRIES",
        "TRANSACTIONS_SLOW_TRANSACTION_THRESHOLD_MILLIS",
        "TRANSACTIONS_CONNECTION_HOLD_THRESHOLD_MILLIS",
        "MYSQL_MAX_SESSIONS",
        "MYSQL_MAX_STATEMENTS",
        "MYSQL_MAX_INDEXES",
        "MYSQL_MAX_TABLES",
        "MYSQL_MAX_LOCK_WAITS",
        "MYSQL_MAX_REPLICATION_CHANNELS",
        "MYSQL_MAX_SETTINGS",
        "DATABASE_ADVISOR_MAX_TABLES",
        "DATABASE_ADVISOR_MAX_COLUMNS",
        "DATABASE_ADVISOR_MAX_INDEXES_PER_TABLE",
        "DATABASE_ADVISOR_MAX_VENDOR_ROWS",
        "ARCHITECTURE_MAX_FILES",
        "ARCHITECTURE_MAX_FILE_BYTES",
        "STARTUP_ENABLED",
        "STARTUP_CAPACITY",
        "APP_PACKAGE",
    ]
    observed = [
        warning.removeprefix("Ignoring invalid SHARPIT_").split(" value")[0]
        for warning in settings.warnings
        if warning.startswith("Ignoring invalid")
    ]
    assert observed == expected


# The runtime-journal byte-size grammar (BootUI DataSize plus the K/M/G short units): digits, then an optional unit,
# any case, with surrounding blanks. The table pins it so a rewrite of the parser cannot change what it accepts.
BYTE_SIZES_ACCEPTED = [
    ("1", 1),
    (" 2 ", 2),
    ("5B", 5),
    ("5b", 5),
    ("3K", 3 * 1024),
    ("3kb", 3 * 1024),
    ("39KB", 39 * 1024),
    ("7M", 7 * 1024**2),
    ("2MB", 2 * 1024**2),
    ("2 mb", 2 * 1024**2),
    ("4G", 4 * 1024**3),
    ("4gb", 4 * 1024**3),
    ("\t8 KB\n", 8 * 1024),
    ("0010MB", 10 * 1024**2),
]
BYTE_SIZES_REJECTED = ["0", "0MB", "-1", "+1", "1.5MB", "1TB", "1 M B", "1MBB", "MB", "abc", "1e3", "1_000", "1KiB"]


@pytest.mark.parametrize(("raw", "expected"), BYTE_SIZES_ACCEPTED)
def test_runtime_journal_max_bytes_accepts(raw: str, expected: int) -> None:
    s = load_settings({}, {"SHARPIT_RUNTIME_JOURNAL_MAX_BYTES": raw})
    assert s.runtime_journal_max_bytes == expected
    assert s.warnings == ()


@pytest.mark.parametrize("raw", BYTE_SIZES_REJECTED)
def test_runtime_journal_max_bytes_rejects(raw: str) -> None:
    s = load_settings({}, {"SHARPIT_RUNTIME_JOURNAL_MAX_BYTES": raw})
    assert s.runtime_journal_max_bytes == 32 * 1024 * 1024
    assert f"Ignoring invalid SHARPIT_RUNTIME_JOURNAL_MAX_BYTES value '{raw}'" in s.warnings


def test_runtime_journal_max_bytes_kwarg_int_and_bool() -> None:
    assert load_settings({"runtime_journal_max_bytes": 4096}, {}).runtime_journal_max_bytes == 4096
    rejected = load_settings({"runtime_journal_max_bytes": True}, {})
    assert rejected.runtime_journal_max_bytes == 32 * 1024 * 1024
