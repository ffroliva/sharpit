"""# derived: BootUI has no dialect resolver; these rows pin the architecture design's §6 decision rules."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from tests.masking import resolver_plants

from sharpit.engine.sqltext import Dialect, resolve

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("row_name", resolver_plants.A12_ROWS, ids=resolver_plants.A12_ROWS)
def test_a12_row(row_name: str) -> None:
    row = resolver_plants.A12_ROWS[row_name]
    for case in row.build():
        assert resolve(*case) is row.wanted


def _scratch_copy(destination: Path) -> Path:
    package = Path(resolve.__globals__["__file__"]).resolve().parents[2]
    copy = destination / "src" / "sharpit"
    shutil.copytree(package, copy, ignore=shutil.ignore_patterns("__pycache__", "static"))
    return copy


@pytest.mark.parametrize("row_name", resolver_plants.A12_ROWS, ids=resolver_plants.A12_ROWS)
def test_each_plant_fails_its_row(row_name: str, tmp_path: Path) -> None:
    row = resolver_plants.A12_ROWS[row_name]
    plant = row.plant
    copy = _scratch_copy(tmp_path)
    target = copy / plant.module
    source = target.read_text(encoding="utf-8")
    assert source.count(plant.anchor) == 1
    target.write_text(source.replace(plant.anchor, plant.replacement, 1), encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(copy.parent), str(ROOT), env.get("PYTHONPATH", "")))
    node = f"tests/masking/test_a12_resolver.py::test_a12_row[{row_name}]"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", node],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0, output[-2000:]
    assert "AssertionError" in output, output[-2000:]
    assert "1 failed" in output, output[-2000:]


def test_the_unseen_database_limit_is_pinned() -> None:
    # Owner's word item 1 remains open: a span without db.system uses the sole application family.
    assert resolver_plants.unseen_database_limit() is Dialect.POSTGRESQL
