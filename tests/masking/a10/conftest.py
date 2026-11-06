"""Shared A10 inputs and result counts."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from sharpit.engine.sqltext import Dialect

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests" / "fixtures" / "sql_errors"
SECTION = re.compile(r"^##### (.+?) #####\n", re.MULTILINE)


def fixture_rows() -> list[tuple[str, Dialect, BaseException]]:
    entries = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    rows = []
    for entry in entries:
        text = (FIXTURES / entry["file"]).read_text(encoding="utf-8")
        parts = SECTION.split(text)
        types = parts[parts.index("types") + 1].splitlines()
        original = next((line.removeprefix("orig: ") for line in types if line.startswith("orig: ")), None)
        if original is None:
            continue
        module, _, name = original.rpartition(".")
        family = {
            "sqlite3": Dialect.SQLITE,
            "aiosqlite": Dialect.SQLITE,
            "psycopg": Dialect.POSTGRESQL,
            "psycopg2": Dialect.POSTGRESQL,
            "asyncpg": Dialect.POSTGRESQL,
            "pymysql": Dialect.MYSQL_FAMILY,
            "mysqlclient": Dialect.MYSQL_FAMILY,
            "aiomysql": Dialect.MYSQL_FAMILY,
        }[entry["driver"]]
        error_type = type(name, (Exception,), {"__module__": module})
        rows.append((entry["file"], family, error_type("fixture error")))
    return rows


@dataclass
class A10Report:
    counts: Counter[str]

    def __init__(self) -> None:
        self.counts = Counter()

    def row(self, evidence: str, expected: Dialect, actual: Dialect) -> None:
        self.counts[evidence] += 1
        if evidence in {"proved", "one_family"}:
            assert actual is expected
            assert actual is not Dialect.UNSUPPORTED


def a10_surface(name: str, drive: Callable[[], Iterable[tuple[str, Dialect, Dialect]]]) -> A10Report:
    """Run one surface's real rows and count their evidence classes."""
    del name  # the caller owns the surface's output assertion
    report = A10Report()
    for evidence, expected, actual in drive():
        report.row(evidence, expected, actual)
    return report


def scratch_package(tmp_path: Path) -> Path:
    package = ROOT / "src" / "sharpit"
    copy = tmp_path / "src" / "sharpit"
    shutil.copytree(package, copy, ignore=shutil.ignore_patterns("__pycache__", "static"))
    return copy


def plant_fails(copy: Path, node: str, module: str, anchor: str, replacement: str) -> None:
    target = copy / module
    source = target.read_text(encoding="utf-8")
    assert source.count(anchor) == 1
    target.write_text(source.replace(anchor, replacement, 1), encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(copy.parent), str(ROOT), env.get("PYTHONPATH", "")))
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
    assert result.returncode == 1, output[-2000:]
    assert "AssertionError" in output, output[-2000:]
    assert "1 failed" in output, output[-2000:]
