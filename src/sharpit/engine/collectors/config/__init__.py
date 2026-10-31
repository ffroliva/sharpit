"""``GET {api}/config`` (port of BootUI ``ConfigService.list``; spec 8 Config, contract 3)."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sharpit.engine.collectors.config.getenv_scan import GetenvFinding, scan_packages
from sharpit.engine.collectors.config.settings_source import ConfigEntry, settings_entries
from sharpit.engine.context import SharpitContext
from sharpit.engine.masking import MASK, Exposure
from sharpit.engine.paging import paged
from sharpit.engine.relaxed import canonicalize, contains

SYSTEM_ENVIRONMENT = "systemEnvironment"
_SCALARS = (str, int, float, bool)


def _scan_roots(ctx: SharpitContext) -> list[Path]:
    """Package directories to scan: ``config_scan`` names, or the caller's top-level package when ``True``."""
    setting = ctx.settings.config_scan
    if setting is False:
        return []
    names = (ctx.caller_module or "",) if setting is True else setting
    roots: list[Path] = []
    for name in names:
        top = name.partition(".")[0]  # find_spec("a.b") imports a; a top-level lookup imports nothing
        if top in ("", "__main__", "sharpit"):
            continue
        try:
            spec = importlib.util.find_spec(top)
        except Exception:  # ValueError for a module without __spec__, ImportError for broken finders
            continue
        # shortcut: a single-module app (main.py) has no package directory and is not scanned; scan its file if needed
        if spec is not None and spec.submodule_search_locations:
            roots.extend(Path(p) for p in spec.submodule_search_locations)
    return roots


def _text(value: object) -> str:
    dump = getattr(value, "model_dump_json", None)  # pydantic models render as one JSON value
    try:
        return str(dump()) if callable(dump) else str(value)
    except Exception:
        return f"<{type(value).__name__}>"


def _display(ctx: SharpitContext, name: str, value: object, secret_typed: bool) -> tuple[object, bool]:
    """What the UI sees and whether it was masked; used for values and defaults alike."""
    exposure = ctx.settings.expose_values
    if secret_typed and exposure is not Exposure.FULL:  # a SecretStr field's default is often a plain str
        return (MASK, True) if exposure is Exposure.MASKED and value is not None else (None, False)
    compound = value is not None and not isinstance(value, _SCALARS) and not hasattr(value, "get_secret_value")
    if compound:
        value = _text(value)  # value detectors only inspect str: a URL or model must be text before masking
    shown, masked = ctx.masker.mask(name, value)
    if compound and not masked and ctx.masker.mask(str(value), value)[1]:
        shown, masked = MASK, True  # a nested key such as "password" inside a model, dict or list
    if shown is not None and not isinstance(shown, _SCALARS):
        shown = _text(shown)  # SecretStr under FULL: pydantic's own placeholder, never the secret
    return shown, masked


def _matches(needle: str, *texts: object) -> bool:
    return any(t is not None and needle in str(t).lower() for t in texts)


def config_report(
    ctx: SharpitContext,
    q: str | None,
    source: str | None,
    overrides_only: bool,
    offset: int | None,
    limit: int | None,
    *,
    environ: Mapping[str, str] = os.environ,
) -> dict[str, Any]:
    # Settings provenance reads the models' .env files; both it and the package scan run once, on first request.
    per_instance = ctx.lazy("config.settings", lambda: [settings_entries(s, environ) for s in ctx.app_settings])
    findings: dict[str, GetenvFinding] = {}
    for finding in ctx.lazy("config.getenv", lambda: scan_packages(_scan_roots(ctx))):
        findings.setdefault(finding.key, finding)

    sources: list[str] = []
    entries: dict[str, ConfigEntry] = {}
    unset: dict[str, ConfigEntry] = {}
    for found, labels in per_instance:
        sources += labels
        for entry in found:
            if entry.value is None and entry.source.startswith("default ("):
                unset.setdefault(entry.name, entry)
            else:
                entries.setdefault(entry.name, entry)
    for name, value in environ.items():
        finding = findings.get(name)
        location, default = (finding.location, finding.default) if finding else (None, None)
        entries.setdefault(name, ConfigEntry(name, value, SYSTEM_ENVIRONMENT, location, default, False))
    sources = list(dict.fromkeys([*sources, SYSTEM_ENVIRONMENT, *(e.source for e in entries.values())]))

    properties: list[dict[str, Any]] = []
    for entry in sorted(entries.values(), key=lambda e: e.name):
        value, value_masked = _display(ctx, entry.name, entry.value, entry.secret_typed)
        default = _display(ctx, entry.name, entry.default, entry.secret_typed)[0]
        properties.append(
            {
                "name": entry.name,
                "value": value,
                "source": entry.source,
                "origin": None,
                "masked": value_masked,  # the value only (contract 3); a masked default shows ****** on its own
                "override": False,
                "description": entry.description,
                "defaultValue": default,
            }
        )

    suggestions: dict[str, dict[str, Any]] = {}
    for name, description, raw_default, secret_typed in [
        *((e.name, e.description, e.default, e.secret_typed) for e in unset.values()),
        *((f.key, f.location, f.default, False) for f in findings.values()),
    ]:
        if name not in entries and name not in suggestions:
            default = _display(ctx, name, raw_default, secret_typed)[0]
            suggestions[name] = {"name": name, "type": None, "description": description, "defaultValue": default}

    # Masking happened above, so q only ever sees displayed values.
    needle = (q or "").strip().lower()
    canonical = canonicalize(needle)
    wanted = (source or "").strip()
    filtered = [
        p
        for p in properties
        if (not wanted or p["source"] == wanted)
        and (not overrides_only or p["override"])
        and (contains(p["name"], canonical) or _matches(needle, p["value"], p["description"], p["defaultValue"]))
    ]
    page, meta = paged(filtered, None, offset, limit, lambda _: ())
    meta["total"] = len(properties)
    return {
        "activeProfiles": list(ctx.profiles),
        "sources": sources,
        "properties": page,
        "propertySuggestions": [
            s
            for _, s in sorted(suggestions.items())
            if contains(s["name"], canonical) or _matches(needle, s["description"])
        ],
        "page": meta,
        "overrideCount": sum(1 for p in properties if p["override"]),
    }
