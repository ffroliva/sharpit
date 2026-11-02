"""Pure classification of incomplete pytest and xdist runs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def partial_run(worker_facts: Sequence[Mapping[str, Any]], controller_facts: Mapping[str, Any]) -> bool:
    """Temporary wrong result for the partial-run contract red."""
    del worker_facts, controller_facts
    return False
