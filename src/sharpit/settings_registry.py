"""Settings parsers, fail-safes, and family-level setting specifications."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import fields
from typing import Any, cast
from urllib.parse import urlsplit

from sharpit.engine.masking import Exposure

_TRUE = {"true", "yes", "on", "1"}
_FALSE = {"false", "no", "off", "0"}
_DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*(ms|s)?", re.IGNORECASE)


def parse_mode(raw: object) -> str | None:
    """``ON``/``OFF``/``AUTO`` from a mode value (true/yes/1 and false/no/0 included, any case), else None."""
    if isinstance(raw, bool):
        return "ON" if raw else "OFF"
    if not isinstance(raw, str):
        return None
    v = raw.strip().lower()
    if v in _TRUE:
        return "ON"
    if v in _FALSE:
        return "OFF"
    return "AUTO" if v == "auto" else None


def parse_bool(raw: object) -> bool:
    if isinstance(raw, bool):
        return raw
    v = raw.strip().lower() if isinstance(raw, str) else None
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    raise ValueError(raw)


def _mode(raw: object) -> str:
    mode = parse_mode(raw)
    if mode is None:
        raise ValueError(raw)
    return mode


def _int(raw: object) -> int:
    if isinstance(raw, int) and not isinstance(raw, bool):
        n = raw
    elif isinstance(raw, str) and re.fullmatch(r"\s*\d+\s*", raw):
        n = int(raw)
    else:
        raise ValueError(raw)
    if n <= 0:
        raise ValueError(raw)
    return n


def _non_negative_int(raw: object) -> int:
    """Like ``_int`` but 0 is allowed: it means "off"."""
    zero = (type(raw) is int and raw == 0) or (isinstance(raw, str) and re.fullmatch(r"\s*0+\s*", raw))
    return 0 if zero else _int(raw)


def _signed_int(raw: object) -> int:
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    if isinstance(raw, str) and re.fullmatch(r"\s*-?\d+\s*", raw):
        return int(raw)
    raise ValueError(raw)


def _min_two_int(raw: object) -> int:
    """N+1 thresholds: one repeat is not a pattern, so anything below 2 counts as 2."""
    return max(2, _non_negative_int(raw))


def _row_limit(raw: object) -> int:
    """PostgreSQL/MySQL row limits: 1..2147483646, so ``limit + 1`` (one past, to detect truncation) fits an int4."""
    n = _int(raw)
    if n > 2147483646:
        raise ValueError(raw)
    return n


_BYTE_UNITS = {"": 1, "B": 1, "K": 1024, "KB": 1024, "M": 1024**2, "MB": 1024**2, "G": 1024**3, "GB": 1024**3}


def _byte_size(raw: object) -> int:
    """Digits, then an optional unit (any case), blanks around either: a scan, no regex to backtrack."""
    if isinstance(raw, int) and not isinstance(raw, bool):
        return _int(raw)
    if not isinstance(raw, str):
        raise ValueError(raw)
    text = raw.strip()
    digits = next((i for i, char in enumerate(text) if not char.isdecimal()), len(text))
    unit = text[digits:].strip().upper()
    if not digits or unit not in _BYTE_UNITS:
        raise ValueError(raw)
    return _int(int(text[:digits]) * _BYTE_UNITS[unit])


# BootUI's JournalSource names; unset means every one. A new source (a W6 sensor's) is added here, nowhere else.
JOURNAL_SOURCES = (
    "http", "sql", "transaction", "connection", "exception", "security", "authorization", "rest-client", "cache",
    "messaging", "scheduled", "log", "mail", "fault-tolerance", "ai", "lifecycle", "gc", "resources", "app-event",
    "websocket", "orm", "agent.executors", "agent.caught-exceptions",
)  # fmt: skip


def _journal_sources(raw: object) -> tuple[str, ...]:
    values = _lower_items(raw)  # JournalSource.parse ignores case
    if any(value not in JOURNAL_SOURCES for value in values):
        raise ValueError(raw)
    return values


def _duration(raw: object) -> float:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        seconds = float(raw)
    elif isinstance(raw, str) and (m := _DURATION.fullmatch(raw.strip())):
        seconds = float(m.group(1)) / (1000 if (m.group(2) or "").lower() == "ms" else 1)
    else:
        raise ValueError(raw)
    if seconds <= 0:
        raise ValueError(raw)
    return seconds


_MODULE_NAME = re.compile(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)*")


def _module_name(raw: object) -> str:
    name = _str(raw)
    if not _MODULE_NAME.fullmatch(name):
        raise ValueError(raw)
    return name


def _str(raw: object) -> str:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    raise ValueError(raw)


def _http_uri(raw: object) -> str:
    value = _str(raw)
    parts = urlsplit(value)
    # urllib's default opener also reads file: and ftp:
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise ValueError(raw)
    return value


def _items(raw: object) -> tuple[str, ...]:
    shown = str(raw)
    if isinstance(raw, str):
        parts: list[Any] = raw.split(",")
    elif isinstance(raw, (list, tuple, set, frozenset)):
        parts = list(cast("Iterable[Any]", raw))
    else:
        raise ValueError(shown)
    if not all(isinstance(p, str) for p in parts):
        raise ValueError(shown)
    return tuple(s for p in parts if (s := str(p).strip()))


def _lower_items(raw: object) -> tuple[str, ...]:
    return tuple(s.lower() for s in _items(raw))


def _exposure(raw: object) -> Exposure:
    if isinstance(raw, Exposure):
        return raw
    try:
        return Exposure(_str(raw).upper())
    except ValueError:
        raise ValueError(raw) from None


def _identity_key(raw: object) -> str:
    value = _str(raw)
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError(raw) from None
    if len(encoded) < 32:
        raise ValueError(raw)
    return value


def _config_scan(raw: object) -> tuple[str, ...] | bool:
    try:
        return parse_bool(raw)
    except ValueError:
        return _items(raw)


# field -> (parser, fail-safe override). None falls back to the default; UNSET makes the field None.
UNSET = object()
_Parser = Callable[[object], Any]
SPECS: dict[str, tuple[_Parser, Any]] = {
    "enabled": (_mode, None),  # handled specially: an invalid value is kept raw so decide() can report it
    "enabled_profiles": (_lower_items, None),
    "disabled_profiles": (_lower_items, None),
    "profile_vars": (_items, None),
    "allow_non_localhost": (parse_bool, False),
    "allowed_hosts": (_items, None),
    "trusted_proxies": (_items, None),
    "trust_container_gateway": (_mode, "OFF"),
    "authentication_token": (_str, None),
    "identity_key": (_identity_key, None),
    "read_only": (parse_bool, True),
    "expose_values": (_exposure, Exposure.MASKED),
    "mask_secrets": (parse_bool, True),
    "show_banner": (parse_bool, True),
    "free_on_idle_enabled": (parse_bool, True),
    "free_on_idle_timeout": (_duration, 300.0),
    "state_dir": (_str, None),
    "config_scan": (_config_scan, None),
    "vulnerabilities_osv_enabled": (parse_bool, False),
    "vulnerabilities_request_timeout": (_duration, None),
    "vulnerabilities_max_packages": (_int, None),
    "vulnerabilities_max_advisories": (_int, None),
    "vulnerabilities_osv_base_uri": (_http_uri, None),
    "vulnerabilities_epss_enabled": (parse_bool, False),
    "vulnerabilities_epss_base_uri": (_http_uri, None),
    "mcp_enabled": (_mode, "OFF"),
    "mcp_max_results": (_int, None),
    "mcp_max_payload_bytes": (_int, None),
    "mcp_max_concurrent_calls": (_int, None),
    "mcp_execution_timeout": (_duration, None),
    "mcp_max_response_bytes": (_int, None),
    "cli_enabled": (parse_bool, False),
    "cli_max_results": (_int, None),
    "cli_max_concurrent_calls": (_int, None),
    "cli_execution_timeout": (_duration, None),
    "http_exchanges_max_exchanges": (_int, None),
    "exceptions_max_groups": (_int, None),
    "exceptions_max_occurrences_per_group": (_int, None),
    "exceptions_max_stack_frames": (_int, None),
    "sql_trace_enabled": (parse_bool, False),
    "sql_trace_sqlite3_enabled": (parse_bool, False),
    "sql_trace_recording": (parse_bool, False),
    "sql_trace_capture_parameters": (parse_bool, False),
    "sql_trace_capture_call_site": (parse_bool, None),
    "sql_trace_max_entries": (_int, None),
    "sql_trace_slow_query_threshold_millis": (_non_negative_int, None),
    "sql_trace_max_sql_length": (_int, None),
    "sql_trace_max_parameter_length": (_int, None),
    "sql_trace_n_plus_one_threshold": (_min_two_int, None),
    "activity_max_entries": (_int, None),
    "activity_request_slow_threshold_ms": (_int, None),
    "activity_n_plus_one_threshold": (_min_two_int, None),
    "activity_unbounded_read_factor": (_min_two_int, None),
    "log_tail_max_lines": (_int, None),
    "log_tail_max_bytes": (_int, None),
    "alembic_config": (_str, UNSET),
    "alembic_timeout": (_duration, None),
    "health_timeout": (_duration, None),
    "threads_max_stack_frames": (_int, None),
    "advisors_max_retained_violations": (_int, None),
    "stream_max_seconds": (_duration, None),
    "ai_token_series_minutes": (_int, None),
    "ai_max_recent_chats": (_int, None),
    "ai_show_content_capture_banner": (parse_bool, None),
    "runtime_journal_enabled": (parse_bool, False),
    "runtime_journal_max_events": (_int, 50_000),
    "runtime_journal_max_bytes": (_byte_size, 32 * 1024 * 1024),
    "runtime_journal_queue_capacity": (_int, 10_000),
    "runtime_journal_sources": (_journal_sources, None),
    "security_logs_max_logs": (_int, None),
    "postgresql_max_sessions": (_row_limit, None),
    "postgresql_max_statements": (_row_limit, None),
    "postgresql_max_indexes": (_row_limit, None),
    "postgresql_max_tables": (_row_limit, None),
    "postgresql_max_vacuum_tables": (_row_limit, None),
    "postgresql_max_replicas": (_row_limit, None),
    "postgresql_max_settings": (_row_limit, None),
    "transactions_enabled": (parse_bool, False),
    "transactions_recording": (parse_bool, False),
    "transactions_max_entries": (_int, None),
    "transactions_slow_transaction_threshold_millis": (_int, None),
    "transactions_connection_hold_threshold_millis": (_int, None),
    "mysql_max_sessions": (_row_limit, None),
    "mysql_max_statements": (_row_limit, None),
    "mysql_max_indexes": (_row_limit, None),
    "mysql_max_tables": (_row_limit, None),
    "mysql_max_lock_waits": (_row_limit, None),
    "mysql_max_replication_channels": (_row_limit, None),
    "mysql_max_settings": (_row_limit, None),
    "database_advisor_max_tables": (_int, None),
    "database_advisor_max_columns": (_int, None),
    "database_advisor_max_indexes_per_table": (_int, None),
    "database_advisor_max_vendor_rows": (_int, None),
    "architecture_max_files": (_int, None),
    "architecture_max_file_bytes": (_int, None),
    "startup_enabled": (parse_bool, False),
    "startup_capacity": (_signed_int, None),
    "app_package": (_module_name, None),
    "copilot_enabled": (_mode, "AUTO"),
    "copilot_session_state_dir": (_str, None),
    "copilot_max_events_per_session": (_int, None),
    "copilot_max_sessions": (_int, None),
    "copilot_max_parsed_sessions": (_int, None),
    "copilot_stream_debounce": (_duration, None),
    "copilot_allow_raw_reveal": (parse_bool, False),
    "claude_code_enabled": (_mode, "AUTO"),
    "claude_code_session_state_dir": (_str, None),
    "claude_code_max_events_per_session": (_int, None),
    "claude_code_max_sessions": (_int, None),
    "claude_code_max_parsed_sessions": (_int, None),
    "claude_code_stream_debounce": (_duration, None),
    "claude_code_allow_raw_reveal": (parse_bool, False),
    "overrides_file": (_str, None),
    "alembic_clean_enabled": (parse_bool, False),
    "dev_services_restart_enabled": (parse_bool, False),
    "cache_clear_enabled": (parse_bool, False),
}

NEVER_ECHOED = {
    "authentication_token",
    "identity_key",
    "vulnerabilities_osv_base_uri",
    "vulnerabilities_epss_base_uri",
}

_FLAG = "Boolean feature flag, not a credential."
_ENTRY_LIMIT = "Entry count limit, not a credential."
_INDEX_LIMIT = "Index count limit, not a credential."
_TABLE_LIMIT = "Table count limit, not a credential."
_SESSION_LIMIT = "Session count limit, not a credential."

_NON_CREDENTIAL_FIELDS = {
    "enabled": "Activation mode, not a credential.",
    "enabled_profiles": "Profile names, not credentials.",
    "disabled_profiles": "Profile names, not credentials.",
    "profile_vars": "Environment variable names, not credentials.",
    "path": "Mount path, not a credential.",
    "api_path": "API mount path, not a credential.",
    "allow_non_localhost": "Boolean access policy, not a credential.",
    "allowed_hosts": "Host names, not credentials.",
    "trusted_proxies": "Proxy addresses, not credentials.",
    "trust_container_gateway": "Boolean trust policy, not a credential.",
    "state_dir": "Local data directory, not a credential.",
    "read_only": "Boolean panel policy, not a credential.",
    "panels": "Panel enablement flags, not credentials.",
    "expose_values": "Exposure mode, not a credential.",
    "mask_secrets": "Boolean masking policy, not a credential.",
    "show_banner": "Boolean display option, not a credential.",
    "free_on_idle_enabled": "Boolean capture retention option, not a credential.",
    "free_on_idle_timeout": "Idle duration before capture is released, not a credential.",
    "config_scan": "Configuration scan selection, not credentials.",
    "vulnerabilities_osv_enabled": _FLAG,
    "vulnerabilities_request_timeout": "Request timeout, not a credential.",
    "vulnerabilities_max_packages": "Package count limit, not a credential.",
    "vulnerabilities_max_advisories": "Advisory count limit, not a credential.",
    "vulnerabilities_epss_enabled": _FLAG,
    "mcp_enabled": "Boolean feature mode, not a credential.",
    "mcp_max_results": "Result count limit, not a credential.",
    "mcp_max_payload_bytes": "Payload size limit, not a credential.",
    "mcp_max_concurrent_calls": "Concurrency limit, not a credential.",
    "mcp_execution_timeout": "Execution timeout, not a credential.",
    "mcp_max_response_bytes": "Response size limit, not a credential.",
    "cli_enabled": _FLAG,
    "cli_max_results": "Result count limit, not a credential.",
    "cli_max_concurrent_calls": "Concurrency limit, not a credential.",
    "cli_execution_timeout": "Execution timeout, not a credential.",
    "http_exchanges_max_exchanges": "Exchange count limit, not a credential.",
    "exceptions_max_groups": "Exception group limit, not a credential.",
    "exceptions_max_occurrences_per_group": "Occurrence count limit, not a credential.",
    "exceptions_max_stack_frames": "Stack frame limit, not a credential.",
    "sql_trace_enabled": _FLAG,
    "sql_trace_sqlite3_enabled": _FLAG,
    "sql_trace_recording": "Boolean recording option, not a credential.",
    "sql_trace_capture_parameters": "Boolean capture option, not a credential.",
    "sql_trace_capture_call_site": "Boolean capture option, not a credential.",
    "sql_trace_max_entries": _ENTRY_LIMIT,
    "sql_trace_slow_query_threshold_millis": "Query duration threshold, not a credential.",
    "sql_trace_max_sql_length": "SQL text size limit, not a credential.",
    "sql_trace_max_parameter_length": "Parameter text size limit, not a credential.",
    "sql_trace_n_plus_one_threshold": "Query count threshold, not a credential.",
    "activity_max_entries": _ENTRY_LIMIT,
    "activity_request_slow_threshold_ms": "Request duration threshold, not a credential.",
    "activity_n_plus_one_threshold": "Query count threshold, not a credential.",
    "activity_unbounded_read_factor": "Read size factor, not a credential.",
    "log_tail_max_lines": "Log line count limit, not a credential.",
    "log_tail_max_bytes": "Log size limit, not a credential.",
    "alembic_timeout": "Migration timeout, not a credential.",
    "alembic_config": "Migration config path, not a credential.",
    "health_timeout": "Health check timeout, not a credential.",
    "threads_max_stack_frames": "Stack frame limit, not a credential.",
    "advisors_max_retained_violations": "Violation count limit, not a credential.",
    "stream_max_seconds": "Stream duration limit, not a credential.",
    "ai_token_series_minutes": "AI token-series window in minutes.",
    "ai_max_recent_chats": "Maximum recent AI chats in the overview.",
    "ai_show_content_capture_banner": "Boolean display option, not a credential.",
    "runtime_journal_enabled": _FLAG,
    "runtime_journal_max_events": "Journal event count limit, not a credential.",
    "runtime_journal_max_bytes": "Journal byte limit, not a credential.",
    "runtime_journal_queue_capacity": "Journal queue count limit, not a credential.",
    "runtime_journal_sources": "Journal source names, not credentials.",
    "security_logs_max_logs": "Log count limit, not a credential.",
    "postgresql_max_sessions": _SESSION_LIMIT,
    "postgresql_max_statements": "Statement count limit, not a credential.",
    "postgresql_max_indexes": _INDEX_LIMIT,
    "postgresql_max_tables": _TABLE_LIMIT,
    "postgresql_max_vacuum_tables": "Vacuum table count limit, not a credential.",
    "postgresql_max_replicas": "Replica count limit, not a credential.",
    "postgresql_max_settings": "Setting count limit, not a credential.",
    "transactions_enabled": _FLAG,
    "transactions_recording": "Boolean recording option, not a credential.",
    "transactions_max_entries": _ENTRY_LIMIT,
    "transactions_slow_transaction_threshold_millis": "Transaction duration threshold, not a credential.",
    "transactions_connection_hold_threshold_millis": "Connection duration threshold, not a credential.",
    "mysql_max_sessions": _SESSION_LIMIT,
    "mysql_max_statements": "Statement count limit, not a credential.",
    "mysql_max_indexes": _INDEX_LIMIT,
    "mysql_max_tables": _TABLE_LIMIT,
    "mysql_max_lock_waits": "Lock wait count limit, not a credential.",
    "mysql_max_replication_channels": "Replication channel count limit, not a credential.",
    "mysql_max_settings": "Setting count limit, not a credential.",
    "database_advisor_max_tables": _TABLE_LIMIT,
    "database_advisor_max_columns": "Column count limit, not a credential.",
    "database_advisor_max_indexes_per_table": _INDEX_LIMIT,
    "database_advisor_max_vendor_rows": "Vendor row count limit, not a credential.",
    "architecture_max_files": "File count limit, not a credential.",
    "architecture_max_file_bytes": "File size limit, not a credential.",
    "startup_enabled": _FLAG,
    "startup_capacity": "Startup step count limit, not a credential.",
    "app_package": "Python package name, not a credential.",
    "copilot_enabled": _FLAG,
    "copilot_session_state_dir": "Session state directory path, not a credential.",
    "copilot_max_events_per_session": "Event count limit, not a credential.",
    "copilot_max_sessions": _SESSION_LIMIT,
    "copilot_max_parsed_sessions": "Parsed session count limit, not a credential.",
    "copilot_stream_debounce": "Stream debounce window, not a credential.",
    "copilot_allow_raw_reveal": "Raw reveal flag, not a credential.",
    "claude_code_enabled": _FLAG,
    "claude_code_session_state_dir": "Session state directory path, not a credential.",
    "claude_code_max_events_per_session": "Event count limit, not a credential.",
    "claude_code_max_sessions": _SESSION_LIMIT,
    "claude_code_max_parsed_sessions": "Parsed session count limit, not a credential.",
    "claude_code_stream_debounce": "Stream debounce window, not a credential.",
    "claude_code_allow_raw_reveal": "Raw reveal flag, not a credential.",
    "overrides_file": "Overrides file path, not a credential.",
    "alembic_clean_enabled": _FLAG,
    "dev_services_restart_enabled": _FLAG,
    "cache_clear_enabled": _FLAG,
    "warnings": "Diagnostic messages, not a credential.",
}


def unclassified_settings_fields(settings_type: object) -> set[str]:
    """Return fields without an explicit credential or non-credential classification."""
    names = {field.name for field in fields(cast(Any, settings_type))}
    return names - NEVER_ECHOED - _NON_CREDENTIAL_FIELDS.keys()
