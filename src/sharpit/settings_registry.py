"""Settings parsers, fail-safes, and family-level setting specifications."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
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


def _min_two_int(raw: object) -> int:
    """N+1 thresholds: one repeat is not a pattern, so anything below 2 counts as 2."""
    return max(2, _non_negative_int(raw))


def _row_limit(raw: object) -> int:
    """PostgreSQL/MySQL row limits: 1..2147483646, so ``limit + 1`` (one past, to detect truncation) fits an int4."""
    n = _int(raw)
    if n > 2147483646:
        raise ValueError(raw)
    return n


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


# field -> (parser, fail-safe override). None falls back to the default; _UNSET makes the field None.
_UNSET = object()
_Parser = Callable[[object], Any]
_SPECS: dict[str, tuple[_Parser, Any]] = {
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
    "alembic_config": (_str, _UNSET),
    "alembic_timeout": (_duration, None),
    "health_timeout": (_duration, None),
    "threads_max_stack_frames": (_int, None),
    "advisors_max_retained_violations": (_int, None),
    "stream_max_seconds": (_duration, None),
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
    "app_package": (_module_name, None),
}

_SECURITY_FIELDS = {
    "allow_non_localhost",
    "allowed_hosts",
    "trusted_proxies",
    "trust_container_gateway",
    "authentication_token",
    "identity_key",
    "read_only",
    "expose_values",
    "mask_secrets",
}
_FAMILY_PREFIXES = {
    "vulnerabilities": "vulnerabilities_",
    "mcp": "mcp_",
    "cli": "cli_",
    "http_exchanges": "http_exchanges_",
    "exceptions": "exceptions_",
    "sql_trace": "sql_trace_",
    "activity": "activity_",
    "log_tail": "log_tail_",
    "alembic": "alembic_",
    "health": "health_",
    "threads": "threads_",
    "advisors": "advisors_",
    "stream": "stream_",
    "security_logs": "security_logs_",
    "postgresql": "postgresql_",
    "transactions": "transactions_",
    "mysql": "mysql_",
    "database_advisor": "database_advisor_",
    "architecture": "architecture_",
}
FAMILY_SPECS: dict[str, dict[str, tuple[_Parser, Any]]] = {}
for _name, _spec in _SPECS.items():
    _family = (
        "security"
        if _name in _SECURITY_FIELDS
        else next((family for family, prefix in _FAMILY_PREFIXES.items() if _name.startswith(prefix)), "core")
    )
    FAMILY_SPECS.setdefault(_family, {})[_name] = _spec

_NEVER_ECHOED = {
    "authentication_token",
    "identity_key",
    "vulnerabilities_osv_base_uri",
    "vulnerabilities_epss_base_uri",
}
NEVER_ECHOED = _NEVER_ECHOED
UNSET = _UNSET
