"""Counts a gate's failing rows against the ``sharpit`` on ``PYTHONPATH`` (``python -m tests.masking.mutant_worker``).

``test_gates_bite`` starts it with a scratch copy of ``src`` that has one mutation applied, and compares its counts with
the unmutated build's. Argument: one JSON object, ``{"surface", "rows", "seeds"}``; output: ``{"visible", "shape"}``.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Sequence

from tests.masking import sql_corpus
from tests.masking import test_statement_surfaces as gates
from tests.masking.sql_corpus import Row


def rows_for(surface: str, rows: int, seeds: Sequence[int]) -> list[Row]:
    """The corpus a surface is read against: its mode's dialect, the same rows in every process."""
    dialect = gates.DIALECTS[gates._mode(surface)]  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    return [row for seed in seeds for row in sql_corpus.rows(seed, rows, dialect)]


def counts(surface: str, rows: Sequence[Row]) -> dict[str, int]:
    found = gates.SURFACES[surface]
    return {
        "visible": len(gates.failures_visible(found, rows)),
        "shape": len(gates.failures_shape(found, rows)),
    }


def main(spec: dict[str, object]) -> dict[str, int]:
    import sharpit  # noqa: PLC0415

    expected = os.path.realpath(os.environ["SHARPIT_MUTANT_SRC"])
    assert os.path.realpath(sharpit.__file__).startswith(expected), sharpit.__file__  # the mutated copy, not the repo
    surface = str(spec["surface"])
    return counts(surface, rows_for(surface, int(str(spec["rows"])), [int(str(seed)) for seed in spec["seeds"]]))  # type: ignore[attr-defined]


if __name__ == "__main__":
    print(json.dumps(main(json.loads(sys.argv[1]))))
