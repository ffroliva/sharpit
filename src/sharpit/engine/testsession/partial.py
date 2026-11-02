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
    """Any selection, deselection, stop, interrupt, or missing collection/run fact makes a run partial."""
    if any(
        facts.get("deselected", 0)
        or facts.get("selection", False)
        or facts.get("interrupted", False)
        or (facts.get("collected") is not None and facts.get("run") is not None and facts["collected"] != facts["run"])
        for facts in worker_facts
    ):
        return True
    return bool(
        controller_facts.get("deselected", 0)
        or controller_facts.get("selection")
        or controller_facts.get("maxfail")
        or controller_facts.get("stopped")
        or controller_facts.get("interrupted")
        or (
            controller_facts.get("collected") is not None
            and controller_facts.get("run") is not None
            and controller_facts["collected"] != controller_facts["run"]
        )
    )
