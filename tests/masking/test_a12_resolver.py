"""# derived: BootUI has no dialect resolver; these rows pin the architecture design's §6 decision rules."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

pytest.importorskip("sqlalchemy")

from tests.masking import resolver_plants
from tests.masking import test_statement_surfaces as gates
from tests.masking.test_gates_bite import DRIVER_SWITCH, UNREAD_HIDES

from sharpit.engine.masking import MASK, Exposure, Masker
from sharpit.engine.sqltext import Dialect, resolve, statement_text

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


# --- A12 on the error surfaces (Task 28) ------------------------------------------------------------------------------
# derived: architecture spec §6, "Text never names a dialect": the rows above, driven through every error surface.

SURFACE_SQL = 'SELECT "c" FROM t'  # a name in generic and PostgreSQL text, a string in MySQL's: the reading shows
NAMED_DRIVERS = ("pymysql", "MySQLdb", "mariadb", "asyncmy", "mysql.connector", "aiomysql", "psycopg", "sqlite3")
SURFACE_ROWS: dict[str, Callable[[], tuple[str, ...]]] = {
    "value_naming_a_driver": lambda: tuple(
        f"literal value contains {name}.Error\n[SQL: {SURFACE_SQL}]" for name in NAMED_DRIVERS
    ),
    "multiline_driver_line": lambda: (f"val\n(pymysql.err.ProgrammingError) failed\n[SQL: {SURFACE_SQL}]",),
    "driver_shaped_value_from_a_trigger": lambda: (
        resolver_plants.trigger_message(f"(pymysql.err.ProgrammingError) failed\n[SQL: {SURFACE_SQL}]"),
    ),
}
# Task 29: a proof that is not MySQL is where a MySQL name on the driver line conflicts; UNSUPPORTED never reads
MODES = {"generic": Dialect.UNSUPPORTED, "mysql_family": Dialect.MYSQL_FAMILY, "postgresql": Dialect.POSTGRESQL}


def _stacktrace(masker: Masker, text: str, dialect: Dialect) -> str | None:
    return gates._attribute("exception.stacktrace", masker, gates.stacktrace_text(text, SURFACE_SQL), dialect)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


SURFACES: dict[str, gates.Driver] = {**gates.ERROR_DRIVERS, "exception_stacktrace": _stacktrace}
# every surface reads the mode as its proof but the test session's, which has no application (owner ruling 2026-11-08,
# cp9-deep S1: the harness gives the other error drivers the mode's proof); with none its proof is step 3
TAKES_THE_DIALECT = set(SURFACES) - gates.NO_PROOF_ERRORS
SURFACE_IDS = [f"{surface}-{mode}-{row}" for surface in SURFACES for mode in MODES for row in SURFACE_ROWS]


@pytest.mark.parametrize("case", SURFACE_IDS, ids=SURFACE_IDS)
def test_a12_surface_row(case: str) -> None:
    surface, mode, row = case.split("-")
    masker = Masker(Exposure.MASKED, True)
    proof = MODES[mode] if surface in TAKES_THE_DIALECT else Dialect.UNSUPPORTED
    read = f"[SQL: {statement_text(masker, SURFACE_SQL, proof)}"
    for text in SURFACE_ROWS[row]():
        shown = SURFACES[surface](masker, text, MODES[mode])
        assert shown is not None
        # hiding too much is caught elsewhere: test_real_error_keeps_statement_and_link (with PROOF) and
        # test_a_sensitive_column_keeps_where on the surfaces that carry a proof
        assert read in shown or f"[SQL: {MASK}]" in shown, shown


# the switch Task 28 removed, put back: on the driver line (test_gates_bite's mutant), and on any line of the head
ANY_LINE_SWITCH = DRIVER_SWITCH._replace(
    replacement=UNREAD_HIDES + "        named = _MYSQL_NAMED.search(text, 0, block.start())\n"
    "        resume, link = _block(masker, text, block.end(), Dialect.MYSQL_FAMILY if named else dialect, shown)\n"
)
SURFACE_PLANTS = {
    "value_naming_a_driver": DRIVER_SWITCH,
    "multiline_driver_line": ANY_LINE_SWITCH,
    "driver_shaped_value_from_a_trigger": DRIVER_SWITCH,
}


@pytest.mark.timeout(300)  # its nested pytest run has its own 120 s timeout: the outer one must outlive it
@pytest.mark.parametrize("row", SURFACE_ROWS)
def test_the_driver_switch_put_back_fails_the_surface_row(row: str, tmp_path: Path) -> None:
    plant = SURFACE_PLANTS[row]
    target = _scratch_copy(tmp_path) / plant.module
    source = target.read_text(encoding="utf-8")
    assert source.count(plant.anchor) == 1
    target.write_text(source.replace(plant.anchor, plant.replacement, 1), encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(tmp_path / "src"), str(ROOT), env.get("PYTHONPATH", "")))
    node = f"tests/masking/test_a12_resolver.py::test_a12_surface_row[exception_stacktrace-postgresql-{row}]"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", node],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip
    output = result.stdout + result.stderr
    assert result.returncode == 1, output[-2000:]
    assert "AssertionError" in output, output[-2000:]
    assert "1 failed" in output, output[-2000:]
