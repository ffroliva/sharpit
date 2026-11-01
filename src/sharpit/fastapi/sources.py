"""``sharpit.attach_sql_sources()``: patch ``sqlite3`` before the app is imported (spec 0.3.0 §8.5)."""

from __future__ import annotations

import os
import sys
from typing import Any

from sharpit.engine.activation import ActivationStatus, active_profiles, decide
from sharpit.engine.sources import sqlite
from sharpit.fastapi.signals import dev_server_signal
from sharpit.settings import load_settings

HOLDER = "api"


def attach_sql_sources(**options: Any) -> ActivationStatus:
    """Attach the raw ``sqlite3`` source for a dev wrapper that must patch before importing the app.

    The decision is ``install()``'s: the same settings, ``decide()`` and the same two SQL trace switches. Capture never
    switches sharpit on by itself, so an inactive status leaves ``sqlite3.connect`` the stdlib function.
    """
    settings = load_settings(options, os.environ)
    status = decide(settings, active_profiles(settings, os.environ), dev_server_signal(sys.argv))
    if status.enabled and settings.sql_trace_enabled and settings.sql_trace_sqlite3_enabled:
        sqlite.attach(HOLDER)
    return status


def detach_sql_sources() -> None:
    """Release ``attach_sql_sources()``'s hold; idempotent. The patch goes once no other holder needs it."""
    sqlite.detach(HOLDER)
