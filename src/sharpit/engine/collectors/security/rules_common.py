"""Small wrappers shared by security rule groups."""

from __future__ import annotations

from collections.abc import Callable

from sharpit.engine.collectors.security import Inputs, Violation

__all__ = ["_production_only"]


def _production_only(check: Callable[[Inputs], list[Violation]]) -> Callable[[Inputs], list[Violation]]:
    def wrapped(inputs: Inputs) -> list[Violation]:
        return check(inputs) if inputs.view.production else []

    return wrapped
