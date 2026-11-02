"""Pure classification of incomplete pytest and xdist runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def selection_requested(args: Sequence[str]) -> bool:
    flags = {"-k", "-m", "--lf", "--last-failed", "--sw", "--stepwise", "--deselect"}
    return any(
        arg in flags
        or arg.startswith(("-k", "-m", "--deselect="))
        or "::" in arg
        or (arg.endswith(".py") and not arg.startswith("-"))
        for arg in args
    )


def partial_run(worker_facts: Sequence[Mapping[str, Any]], controller_facts: Mapping[str, Any]) -> bool:
    """Temporary wrong result for the baseline refusal red."""
    del worker_facts, controller_facts
    return False
