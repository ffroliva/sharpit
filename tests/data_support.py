"""Shared by the data panel tests: a spy on every SQLAlchemy entry point that configures mappers."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import orm


def spy_on_configure(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Names of every SQLAlchemy entry point that would configure mappers, recorded when called."""
    calls: list[str] = []
    for owner, name in (
        (orm, "configure_mappers"),
        (orm.Mapper, "_check_configure"),
        (sys.modules["sqlalchemy.orm.mapper"], "_configure_registries"),
    ):
        original: Callable[..., Any] = getattr(owner, name)

        def spy(*args: Any, _name: str = name, _original: Callable[..., Any] = original, **kwargs: Any) -> Any:
            calls.append(_name)
            return _original(*args, **kwargs)

        monkeypatch.setattr(owner, name, spy)
    return calls
