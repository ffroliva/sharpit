"""Settings (port of the BootUI ``bootui.*`` properties).

Every property ``bootui.<a>.<b-c>`` is the env var ``SHARPIT_<A>_<B_C>`` and the ``install()`` kwarg / dataclass field
``a_b_c``. Env overrides kwargs; an empty env value is unset. An invalid value never raises: the field takes its
**fail-safe** value (the safest reading, not always the default) and a warning is recorded. Only ``path`` and
``api_path`` raise ``ValueError``, because the mount cannot be built without them.
"""

from __future__ import annotations

import dataclasses
import difflib
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, cast

from sharpit.engine.masking import Exposure
from sharpit.engine.panels import PANELS


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
    authentication_token: str | None = None
    read_only: bool = False
    panels: Mapping[str, PanelSettings] = field(default_factory=lambda: {p.id: PanelSettings() for p in PANELS})
    expose_values: Exposure = Exposure.MASKED
    mask_secrets: bool = True
    show_banner: bool = True
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
    log_tail_max_lines: int = 500
    log_tail_max_bytes: int = 1048576
    alembic_config: str | None = "alembic.ini"
    alembic_timeout: float = 5.0
    health_timeout: float = 5.0
    threads_max_stack_frames: int = 64
    advisors_max_retained_violations: int = 10000
    stream_max_seconds: float = 3.0
    warnings: tuple[str, ...] = ()


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


def _bool(raw: object) -> bool:
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


def _str(raw: object) -> str:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    raise ValueError(raw)


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


def _config_scan(raw: object) -> tuple[str, ...] | bool:
    try:
        return _bool(raw)
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
    "allow_non_localhost": (_bool, False),
    "allowed_hosts": (_items, None),
    "trusted_proxies": (_items, None),
    "trust_container_gateway": (_mode, "OFF"),
    "authentication_token": (_str, None),
    "read_only": (_bool, True),
    "expose_values": (_exposure, Exposure.MASKED),
    "mask_secrets": (_bool, True),
    "show_banner": (_bool, True),
    "state_dir": (_str, None),
    "config_scan": (_config_scan, None),
    "vulnerabilities_osv_enabled": (_bool, False),
    "vulnerabilities_request_timeout": (_duration, None),
    "vulnerabilities_max_packages": (_int, None),
    "vulnerabilities_max_advisories": (_int, None),
    "vulnerabilities_osv_base_uri": (_str, None),
    "vulnerabilities_epss_enabled": (_bool, False),
    "vulnerabilities_epss_base_uri": (_str, None),
    "mcp_enabled": (_mode, "OFF"),
    "mcp_max_results": (_int, None),
    "mcp_max_payload_bytes": (_int, None),
    "mcp_max_concurrent_calls": (_int, None),
    "mcp_execution_timeout": (_duration, None),
    "mcp_max_response_bytes": (_int, None),
    "cli_enabled": (_bool, False),
    "cli_max_results": (_int, None),
    "cli_max_concurrent_calls": (_int, None),
    "cli_execution_timeout": (_duration, None),
    "http_exchanges_max_exchanges": (_int, None),
    "exceptions_max_groups": (_int, None),
    "exceptions_max_occurrences_per_group": (_int, None),
    "exceptions_max_stack_frames": (_int, None),
    "sql_trace_enabled": (_bool, False),
    "sql_trace_recording": (_bool, False),
    "sql_trace_capture_parameters": (_bool, False),
    "sql_trace_capture_call_site": (_bool, None),
    "sql_trace_max_entries": (_int, None),
    "sql_trace_slow_query_threshold_millis": (_non_negative_int, None),
    "sql_trace_max_sql_length": (_int, None),
    "sql_trace_max_parameter_length": (_int, None),
    "sql_trace_n_plus_one_threshold": (_min_two_int, None),
    "activity_max_entries": (_int, None),
    "activity_request_slow_threshold_ms": (_int, None),
    "activity_n_plus_one_threshold": (_min_two_int, None),
    "log_tail_max_lines": (_int, None),
    "log_tail_max_bytes": (_int, None),
    "alembic_config": (_str, _UNSET),
    "alembic_timeout": (_duration, None),
    "health_timeout": (_duration, None),
    "threads_max_stack_frames": (_int, None),
    "advisors_max_retained_violations": (_int, None),
    "stream_max_seconds": (_duration, None),
}
_DEFAULTS = SharpitSettings()
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
    unknown = sorted(str(k) for k in given if k not in known)
    if unknown:
        raise ValueError(f"Unknown sharpit panel(s): {', '.join(unknown)}; known panels: {', '.join(known)}")
    out: dict[str, PanelSettings] = {}
    for pid in known:
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
                warnings.append(f"Ignoring invalid {env} value '{raw}'")
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
            # install() logs warnings: never echo a token, however malformed
            shown = "" if name == "authentication_token" else f" '{raw}'"
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

    values["panels"] = _panels(kwargs, environ, warnings)
    if values.get("expose_values") is Exposure.FULL:
        warnings.append("SHARPIT_EXPOSE_VALUES=FULL exposes unmasked secrets")
    return SharpitSettings(**values, warnings=tuple(warnings))
