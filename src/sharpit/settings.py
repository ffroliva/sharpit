"""Settings (port of the BootUI ``bootui.*`` properties).

Every property ``bootui.<a>.<b-c>`` is the env var ``SHARPIT_<A>_<B_C>`` and the ``install()`` kwarg / dataclass field
``a_b_c``. Env overrides kwargs; an empty env value is unset. An invalid value never raises: the field takes its
**fail-safe** value (the safest reading, not always the default) and a warning is recorded. Only ``path`` and
``api_path`` raise ``ValueError``, because the mount cannot be built without them.
"""

from __future__ import annotations

import dataclasses
import difflib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast

from sharpit import settings_registry as _registry
from sharpit.engine.masking import Exposure
from sharpit.engine.panels import PANELS

_NEVER_ECHOED = _registry.NEVER_ECHOED
_JOURNAL_SOURCES = _registry.JOURNAL_SOURCES
_SPECS = _registry.SPECS
_UNSET = _registry.UNSET
_bool = _registry.parse_bool
parse_mode = _registry.parse_mode
# Keep names that were visible from this module before the parser split.
_registry_internal = cast(Any, _registry)
Callable = _registry.Callable
Iterable = _registry.Iterable
re = _registry.re
urlsplit = _registry.urlsplit
_DURATION = _registry_internal._DURATION
_FALSE = _registry_internal._FALSE
_MODULE_NAME = _registry_internal._MODULE_NAME
_Parser = _registry_internal._Parser
_TRUE = _registry_internal._TRUE
_config_scan = _registry_internal._config_scan
_duration = _registry_internal._duration
_exposure = _registry_internal._exposure
_http_uri = _registry_internal._http_uri
_identity_key = _registry_internal._identity_key
_int = _registry_internal._int
_items = _registry_internal._items
_lower_items = _registry_internal._lower_items
_min_two_int = _registry_internal._min_two_int
_mode = _registry_internal._mode
_module_name = _registry_internal._module_name
_non_negative_int = _registry_internal._non_negative_int
_row_limit = _registry_internal._row_limit
_str = _registry_internal._str
del _registry_internal
del _registry


@dataclass(frozen=True)
class PanelSettings:
    enabled: bool = True
    read_only: bool = False


@dataclass(frozen=True)
class SharpitSettings:
    enabled: str = "AUTO"
    enabled_profiles: tuple[str, ...] = ("dev", "local", "development")
    disabled_profiles: tuple[str, ...] = ("prod", "production")
    profile_vars: tuple[str, ...] = ("SHARPIT_PROFILES", "APP_ENV", "ENVIRONMENT")
    path: str = "/sharpit"
    api_path: str = "/sharpit/api"
    allow_non_localhost: bool = False
    allowed_hosts: tuple[str, ...] = ()
    trusted_proxies: tuple[str, ...] = ()
    trust_container_gateway: str = "OFF"
    authentication_token: str | None = field(default=None, repr=False)
    identity_key: str | None = field(default=None, repr=False)
    read_only: bool = False
    panels: Mapping[str, PanelSettings] = field(default_factory=lambda: {p.id: PanelSettings() for p in PANELS})
    expose_values: Exposure = Exposure.MASKED
    mask_secrets: bool = True
    show_banner: bool = True
    free_on_idle_enabled: bool = True
    free_on_idle_timeout: float = 300.0
    state_dir: str = ".sharpit"
    config_scan: tuple[str, ...] | bool = True
    vulnerabilities_osv_enabled: bool = True
    vulnerabilities_request_timeout: float = 10.0
    vulnerabilities_max_packages: int = 500
    vulnerabilities_max_advisories: int = 200
    vulnerabilities_osv_base_uri: str = "https://api.osv.dev"
    vulnerabilities_epss_enabled: bool = True
    vulnerabilities_epss_base_uri: str = "https://api.first.org"
    mcp_enabled: str = "OFF"
    mcp_max_results: int = 200
    mcp_max_payload_bytes: int = 1048576
    mcp_max_concurrent_calls: int = 20
    mcp_execution_timeout: float = 30.0
    mcp_max_response_bytes: int = 4194304
    cli_enabled: bool = True
    cli_max_results: int = 200  # BootUI docs/PROPERTIES.md bootui.cli.*
    cli_max_concurrent_calls: int = 20
    cli_execution_timeout: float = 30.0
    # 0.2.0 (spec §12)
    http_exchanges_max_exchanges: int = 200
    exceptions_max_groups: int = 100
    exceptions_max_occurrences_per_group: int = 25
    exceptions_max_stack_frames: int = 50
    sql_trace_enabled: bool = True
    sql_trace_sqlite3_enabled: bool = True  # sharpit-only: the raw sqlite3 source (spec 0.3.0 §10)
    sql_trace_recording: bool = True
    sql_trace_capture_parameters: bool = False
    sql_trace_capture_call_site: bool = True
    sql_trace_max_entries: int = 200
    sql_trace_slow_query_threshold_millis: int = 100  # 0 disables
    sql_trace_max_sql_length: int = 2000
    sql_trace_max_parameter_length: int = 200
    sql_trace_n_plus_one_threshold: int = 5  # min 2
    activity_max_entries: int = 200
    activity_request_slow_threshold_ms: int = 1000
    activity_n_plus_one_threshold: int = 5  # min 2
    activity_unbounded_read_factor: int = 2  # min 2; T-unbounded-read
    log_tail_max_lines: int = 500
    log_tail_max_bytes: int = 1048576
    alembic_config: str | None = "alembic.ini"
    alembic_timeout: float = 5.0
    health_timeout: float = 5.0
    threads_max_stack_frames: int = 64
    advisors_max_retained_violations: int = 10000
    stream_max_seconds: float = 3.0
    ai_token_series_minutes: int = 60
    ai_max_recent_chats: int = 100
    ai_show_content_capture_banner: bool = True
    runtime_journal_enabled: bool = True
    runtime_journal_max_events: int = 50_000
    runtime_journal_max_bytes: int = 32 * 1024 * 1024
    runtime_journal_queue_capacity: int = 10_000
    runtime_journal_sources: tuple[str, ...] = _JOURNAL_SOURCES
    agent_sensors: tuple[str, ...] = ()  # none: BootUI's default set would leave a hook that cannot be removed (W6 S3)
    runtime_insights_ai_token_threshold: int = 8000  # tokens of one model call (AiUsageByRoute.java:35)
    resources_jfr_max_duration: float = 30.0  # 1s..600s; read by the resource-profile floor (W5c I2)
    # 0.4.0 panels: pre-created by lane F, inert until the owning lane reads them (F-foundation.md interface table)
    security_logs_max_logs: int = 500
    postgresql_max_sessions: int = 100
    postgresql_max_statements: int = 100
    postgresql_max_indexes: int = 500
    postgresql_max_tables: int = 200
    postgresql_max_vacuum_tables: int = 200
    postgresql_max_replicas: int = 10
    postgresql_max_settings: int = 40
    transactions_enabled: bool = True
    transactions_recording: bool = True
    transactions_max_entries: int = 200
    transactions_slow_transaction_threshold_millis: int = 200
    transactions_connection_hold_threshold_millis: int = 500
    # 0.5.0 committed lanes (spec §4.5): BootUI's bootui.mysql.* (WAVE-A §6), BootUI's fixed database-advisor scan
    # bounds (WAVE-A §4, settable here), the app-source index bounds (spec §4.2) and the app package override
    mysql_max_sessions: int = 100
    mysql_max_statements: int = 100
    mysql_max_indexes: int = 500
    mysql_max_tables: int = 200
    mysql_max_lock_waits: int = 100
    mysql_max_replication_channels: int = 10
    mysql_max_settings: int = 40
    database_advisor_max_tables: int = 300
    database_advisor_max_columns: int = 300
    database_advisor_max_indexes_per_table: int = 100
    database_advisor_max_vendor_rows: int = 500
    architecture_max_files: int = 2000
    architecture_max_file_bytes: int = 524288
    startup_enabled: bool = True
    startup_capacity: int = 4096
    github_api_enabled: bool = True
    github_request_timeout: float = 5.0
    github_max_pull_requests: int = 10
    github_max_issues: int = 25
    github_max_security_alerts: int = 50
    github_max_workflow_runs: int = 20
    github_quota_safety_threshold: int = 10
    github_max_api_calls: int = 17
    github_allowed_api_hosts: tuple[str, ...] = ("api.github.com",)
    app_package: str | None = None  # dotted name, resolved through sys.modules only (never imported)
    copilot_enabled: str = "AUTO"
    copilot_session_state_dir: str | None = None
    copilot_max_events_per_session: int = 2000
    copilot_max_sessions: int = 100
    copilot_max_parsed_sessions: int = 100
    copilot_stream_debounce: float = 0.4
    copilot_allow_raw_reveal: bool = False
    claude_code_enabled: str = "AUTO"
    claude_code_session_state_dir: str | None = None
    claude_code_max_events_per_session: int = 2000
    claude_code_max_sessions: int = 100
    claude_code_max_parsed_sessions: int = 100
    claude_code_stream_debounce: float = 0.4
    claude_code_allow_raw_reveal: bool = False
    # 0.6.0 W8 action gates (BootUI P:118,357,1009; alembic clean is sharpit-only, Q9)
    overrides_file: str = ".sharpit/overrides.env"  # load_settings derives it from state_dir when unset
    alembic_clean_enabled: bool = False
    dev_services_restart_enabled: bool = False
    cache_clear_enabled: bool = True
    warnings: tuple[str, ...] = ()


_DEFAULTS = SharpitSettings()
WEAK_IDENTITY_KEY = "SHARPIT_IDENTITY_KEY is one character repeated: a weak key"
# owner 2026-11-07, item 7: capture on shows more than bound values, so install says so, as FULL does
CAPTURE_SHOWS_VALUES = (
    "SHARPIT_SQL_TRACE_CAPTURE_PARAMETERS=true shows SQL inline literals and error text unmasked, with bound values"
)
_FIELDS = {f.name for f in dataclasses.fields(SharpitSettings)} - {"warnings"}


def _with_suggestion(name: str) -> str:
    close = difflib.get_close_matches(name, sorted(_FIELDS), n=1)
    return f"{name} (did you mean '{close[0]}'?)" if close else name


def _env_name(name: str) -> str:
    return "SHARPIT_" + name.upper()


def _pick(environ: Mapping[str, str], env: str, kwargs: Mapping[str, object], key: str) -> object | None:
    """Env wins over kwargs; an empty or blank value counts as unset."""
    raw = environ.get(env)
    if raw is not None and raw.strip():
        return raw
    value = kwargs.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return value


def _panels(kwargs: Mapping[str, object], environ: Mapping[str, str], warnings: list[str]) -> dict[str, PanelSettings]:
    raw_panels = kwargs.get("panels")
    if raw_panels is None:
        raw_panels = {}
    if not isinstance(raw_panels, Mapping):
        raise TypeError("panels must be a mapping of panel id to PanelSettings")
    given = cast("Mapping[str, Any]", raw_panels)
    known = [p.id for p in PANELS]
    accepted = [p.id for p in PANELS if p.implemented]  # an unimplemented 0.4 panel is as unknown as a typo
    unknown = sorted(str(k) for k in given if k not in accepted)
    if unknown:
        raise ValueError(f"Unknown sharpit panel(s): {', '.join(unknown)}; known panels: {', '.join(accepted)}")
    out: dict[str, PanelSettings] = {}
    for pid in known:
        if pid not in accepted:  # unimplemented: defaults only; its SHARPIT_PANELS_<ID>_* env is ignored
            out[pid] = PanelSettings()
            continue
        base = given.get(pid)
        flags: dict[str, object] = {"enabled": True, "read_only": False}
        if isinstance(base, PanelSettings):
            flags = {"enabled": base.enabled, "read_only": base.read_only}
        elif isinstance(base, Mapping):
            given_flags = cast("Mapping[str, object]", base)
            bad = sorted(str(k) for k in given_flags if k not in flags)
            if bad:
                raise ValueError(
                    f"Unknown flag(s) for sharpit panel {pid}: {', '.join(bad)}; known flags: enabled, read_only"
                )
            flags.update({k: given_flags[k] for k in flags if k in given_flags})
        for key, failsafe in (("enabled", False), ("read_only", True)):
            env = f"SHARPIT_PANELS_{pid.upper().replace('-', '_')}_{key.upper()}"
            raw = _pick(environ, env, flags, key)
            if raw is None:
                if not isinstance(flags[key], bool):  # given as None or blank: fail safe, never open
                    flags[key] = failsafe
                continue
            try:
                flags[key] = _bool(raw)
            except ValueError:
                shown = f" '{raw}'"
                warnings.append(f"Ignoring invalid {env} value{shown}")
                flags[key] = failsafe
        out[pid] = PanelSettings(enabled=bool(flags["enabled"]), read_only=bool(flags["read_only"]))
    return out


def load_settings(kwargs: Mapping[str, object], environ: Mapping[str, str]) -> SharpitSettings:
    unknown = sorted(set(kwargs) - _FIELDS)
    if unknown:
        raise TypeError(f"Unknown sharpit setting(s): {', '.join(_with_suggestion(name) for name in unknown)}")

    warnings: list[str] = []
    values: dict[str, Any] = {}
    for name, (parse, failsafe) in _SPECS.items():
        env = _env_name(name)
        raw = _pick(environ, env, kwargs, name)
        if raw is None:
            continue
        try:
            value = parse(raw)
        except ValueError:
            # install() logs warnings: never echo a token, however malformed, or a URI that can carry credentials
            shown = "" if name in _NEVER_ECHOED else f" '{raw}'"
            warnings.append(f"Ignoring invalid {env} value{shown}")
            # `enabled` keeps the raw text so decide() reports it; other fields take their fail-safe (or default).
            if name == "enabled":
                values[name] = str(raw).strip()
            elif failsafe is _UNSET:
                values[name] = None
            elif failsafe is not None:
                values[name] = failsafe
            continue
        if isinstance(raw, str) and value == () and isinstance(getattr(_DEFAULTS, name), tuple):
            continue  # a blank list string falls back to the default; an explicit empty list or tuple clears it
        values[name] = value

    # path / api_path are validated, never defaulted silently.
    path = _pick(environ, "SHARPIT_PATH", kwargs, "path")
    path = _DEFAULTS.path if path is None else str(path).strip()
    if not path.startswith("/"):
        raise ValueError(f"path must start with '/': {path!r}")
    if path == "/":  # the mount would shadow every host route, even while inactive
        raise ValueError("path must not be '/': sharpit needs its own prefix such as '/sharpit'")
    if path.endswith("/"):
        raise ValueError(f"path must not end with '/': {path!r}")
    raw_api = _pick(environ, "SHARPIT_API_PATH", kwargs, "api_path")
    api_path = f"{path}/api" if raw_api is None else str(raw_api).strip()
    rest = api_path[len(path) + 1 :]
    if not api_path.startswith(path + "/") or not rest or not all(rest.split("/")):
        raise ValueError(f"api_path must be '{path}/' followed by one or more segments: {api_path!r}")
    values["path"], values["api_path"] = path, api_path

    if "overrides_file" not in values:
        values["overrides_file"] = f"{values.get('state_dir', _DEFAULTS.state_dir)}/overrides.env"
    values["panels"] = _panels(kwargs, environ, warnings)
    if values.get("expose_values") is Exposure.FULL:
        warnings.append("SHARPIT_EXPOSE_VALUES=FULL exposes unmasked secrets")
    if values.get("sql_trace_capture_parameters") and values.get("expose_values") is not Exposure.METADATA_ONLY:
        warnings.append(CAPTURE_SHOWS_VALUES)
    if len(set(values.get("identity_key") or "ab")) == 1:
        warnings.append(WEAK_IDENTITY_KEY)
    return SharpitSettings(**values, warnings=tuple(warnings))
