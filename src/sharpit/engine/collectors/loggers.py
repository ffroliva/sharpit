"""``GET {api}/loggers`` and ``POST {api}/loggers/{name}`` (port of BootUI ``LoggersService``; spec 8 Loggers)."""

from __future__ import annotations

import logging
from typing import Any

from sharpit.engine.paging import BadRequest, paged

AVAILABLE_LEVELS = ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"]
_ROOT = "ROOT"
_OWN = "sharpit"


def _is_own(name: str) -> bool:
    return name == _OWN or name.startswith(_OWN + ".")


def _dto(name: str, logger: logging.Logger) -> dict[str, Any]:
    configured = None if logger.level == logging.NOTSET else logging.getLevelName(logger.level)
    return {
        "name": name,
        "configuredLevel": configured,
        "effectiveLevel": logging.getLevelName(logger.getEffectiveLevel()),
    }


def loggers_report(q: str | None, offset: int | None, limit: int | None) -> dict[str, Any]:
    # Read the registry directly: getLogger() on a name would create it, and PlaceHolders are not loggers.
    registry = logging.root.manager.loggerDict
    entries = [
        _dto(name, lg) for name, lg in list(registry.items()) if isinstance(lg, logging.Logger) and not _is_own(name)
    ]
    entries.append(_dto(_ROOT, logging.root))
    entries.sort(key=lambda e: e["name"])
    page, meta = paged(entries, q, offset, limit, lambda e: (e["name"],))
    return {"availableLevels": AVAILABLE_LEVELS, "loggers": page, "page": meta}


def set_level(name: str, level: str | None) -> dict[str, Any]:
    """Set (or reset, for a blank level) one logger's level; process-local and runtime only."""
    if not name:
        raise BadRequest("'name' must be provided")
    if _is_own(name):
        raise BadRequest(f"Refusing to change the level of sharpit's own logger '{name}'.")
    wanted = (level or "").strip().upper()
    if wanted and wanted not in AVAILABLE_LEVELS:
        raise BadRequest(f"Unknown level '{level}'")
    is_root = name in (_ROOT, "root")
    logger = logging.root if is_root else logging.getLogger(name)
    number = logging.getLevelNamesMapping()[wanted] if wanted else logging.WARNING if is_root else logging.NOTSET
    logger.setLevel(number)
    return _dto(_ROOT if is_root else name, logger)
