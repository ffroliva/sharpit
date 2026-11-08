"""Every planted build of the live oracle still finds its line, offline: a vanished anchor fails here, with no server.

The live suite runs only on a box with servers, so a refactor that rewrites a planted line (Task 29 rewrote the
PostgreSQL backslash cut) would otherwise surface only there, as a control that "survives" for the wrong reason.
"""

# derived: Task 29 live gate, test_oracle_control[scs_off_no_cut]; no BootUI source

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from tests.live import test_server_oracle as live  # noqa: E402
from tests.masking.test_gates_bite import LEXER_MODULE, Mutant  # noqa: E402

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "sharpit"
LEXER = Path(*LEXER_MODULE.split(".")[1:]).with_suffix(".py")
PLANTS: dict[str, Mutant] = {
    **{name: value for name, value in vars(live).items() if isinstance(value, Mutant)},
    **{f"CONTROLS[{name}]": mutant for name, (_, _, mutant) in live.CONTROLS.items()},
}


def test_the_live_suite_has_plants() -> None:
    assert len(PLANTS) >= 8


@pytest.mark.parametrize("name", PLANTS)
def test_every_live_plant_finds_its_line_once(name: str) -> None:
    mutant = PLANTS[name]
    target = PACKAGE / (Path(mutant.module) if mutant.module else LEXER)
    assert target.read_text(encoding="utf-8").count(mutant.anchor) == 1, f"{name}: {mutant.anchor!r} in {target}"


# the statement runs on SQLite under an engine that names MySQL: what reaches the recorder is the wiring's reading
_PROBE = """
import sqlalchemy as sa
from fastapi import FastAPI
from sharpit import install

engine = sa.create_engine("sqlite://")
engine.dialect.name = "mysql"
handle = install(FastAPI(), enabled="ON", show_banner=False, sql_trace_sqlite3_enabled=False, engines=[engine])
with engine.connect() as conn:
    conn.exec_driver_sql("SELECT 1")
print(handle.context.capture.sql_trace.rows()[-1]["shape"].dialect.name)
handle.uninstall_capture()
"""


def test_the_wrong_wired_plant_reaches_the_recorder(tmp_path: Path) -> None:
    """``test_a_wrong_wired_dialect_fails_the_oracle`` proves something only if its plant changes the reading the
    recorder uses. Task 29 made a conflict hide whole, so a plant that only makes the event disagree with its engine
    leaks nothing and the live control cannot bite."""
    import os
    import subprocess
    import sys

    from tests.masking.test_gates_bite import _mutate, _scratch_copy  # pyright: ignore[reportPrivateUsage]

    _mutate(_scratch_copy(tmp_path), live.WRONG_WIRED)
    env = {**os.environ, "PYTHONPATH": str(tmp_path / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run(
        [sys.executable, "-c", _PROBE], env=env, capture_output=True, text=True, check=False, timeout=120
    )
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip().splitlines()[-1] == "POSTGRESQL"
