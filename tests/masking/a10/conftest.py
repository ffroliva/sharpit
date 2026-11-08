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
CLASS_ONLY = re.compile(r"^(?:\([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\)|[A-Za-z_]\w*)$")


def fixture_rows() -> list[tuple[str, Dialect, BaseException, str]]:
    entries = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    rows = []
    for entry in entries:
        text = (FIXTURES / entry["file"]).read_text(encoding="utf-8")
        parts = SECTION.split(text)
        types = parts[parts.index("types") + 1].splitlines()
        original = next((line.removeprefix("orig: ") for line in types if line.startswith("orig: ")), None)
        modules = {"aiosqlite": "sqlite3", "mysqlclient": "MySQLdb"}
        module, _, name = (
            original.rpartition(".") if original else (modules.get(entry["driver"], entry["driver"]), "", "Error")
        )
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
        raw = parts[parts.index("str(exc)") + 1].strip()
        orig_text = parts[parts.index("str(exc.orig)") + 1].strip() if "str(exc.orig)" in parts else ""
        code = re.match(r"\((\d+),", orig_text)
        msg = orig_text or raw
        args: tuple[object, ...] = (int(code[1]), msg) if code else (msg,)
        original_error = type(name, (Exception,), {"__module__": module})(*args)
        error_type = type(
            "DBAPIError", (Exception,), {"__module__": "sqlalchemy.exc", "__str__": lambda _self, text=raw: text}
        )
        error = error_type(raw)
        error.orig = original_error
        block = re.search(r"^\[SQL: (.*?)\]$", raw, re.MULTILINE | re.DOTALL)
        if block:
            error.statement = block[1]
        rows.append((entry["file"], family, error, raw))
    return rows


@dataclass
class A10Report:
    counts: Counter[str]

    def __init__(self) -> None:
        self.counts = Counter()

    def row(self, evidence: str, expected: Dialect, actual: Dialect) -> None:
        self.counts[evidence] += 1
        if evidence in {"source_chain", "one_family"}:
            assert actual is expected
            assert actual is not Dialect.UNSUPPORTED


def a10_surface(name: str, drive: Callable[[], Iterable[tuple[str, Dialect, Dialect, str, str]]]) -> A10Report:
    """Run one surface's real rows and count their evidence classes."""
    del name  # the caller owns the surface's output assertion
    report = A10Report()
    for evidence, expected, actual, rendered, known_word in drive():
        report.row(evidence, expected, actual)
        if evidence in {"source_chain", "one_family"}:
            if CLASS_ONLY.fullmatch(rendered):
                report.counts["class_only"] += 1
                assert known_word not in rendered
            else:
                assert known_word in rendered
    if report.counts["source_chain"]:
        assert report.counts["class_only"] == 16
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
