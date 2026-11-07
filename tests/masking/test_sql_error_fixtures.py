"""The captured driver error text is what the later error-rendering tests read: check it is all there.

The fixtures are written by ``scripts/dev/capture_sql_errors.py`` from live databases. These tests do not
render anything; they only guard the corpus (Task 7 tests ``mask_error`` against it).
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "sql_errors"
MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
KEYS = {
    "case",
    "driver",
    "file",
    "driver_version",
    "sqlalchemy_version",
    "server_version",
    "marker",
    "marker_in_text",
    "sections",
}
REQUIRED_DRIVERS = {"sqlite3", "aiosqlite", "psycopg2", "asyncpg", "pymysql"}
# Nothing from the machine that captured them may sit in a public repo.
PERSONAL = re.compile(r"[A-Za-z]:\\Users\\|/Users/|/home/|\\Temp\\", re.IGNORECASE)


def problems(entry: dict[str, object], root: Path) -> list[str]:
    """Everything wrong with one manifest entry against the files under ``root``."""
    found = [f"missing key {k}" for k in sorted(KEYS - entry.keys())]
    if found:
        return found
    path = root / str(entry["file"])
    if not path.is_file():
        return [f"{entry['file']}: file is missing"]
    text = path.read_bytes().decode("utf-8")
    has_marker = str(entry["marker"]) in text
    if has_marker != entry["marker_in_text"]:
        found.append(f"{entry['file']}: marker_in_text={entry['marker_in_text']} but the file says {has_marker}")
    # Through SQLAlchemy the statement block always carries it; only a bare driver may leave the value out.
    if not has_marker and not str(entry["case"]).startswith("raw_"):
        found.append(f"{entry['file']}: planted marker {entry['marker']} is not in the file")
    sections = entry["sections"]
    assert isinstance(sections, list)
    found += [f"{entry['file']}: section {s!r} is missing" for s in sections if f"##### {s} #####\n" not in text]
    if not str(entry["file"]).startswith(f"{entry['driver']}/"):
        found.append(f"{entry['file']}: not under its driver directory {entry['driver']}")
    found += [f"{entry['file']}: empty {k}" for k in ("driver_version", "server_version") if not entry[k]]
    return found


def test_the_manifest_covers_the_required_drivers() -> None:
    assert {e["driver"] for e in MANIFEST} >= REQUIRED_DRIVERS


def test_the_manifest_matches_the_files() -> None:
    on_disk = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*.txt")}
    assert on_disk == {e["file"] for e in MANIFEST}


def test_manifest_entries_are_unique() -> None:
    assert len({(e["driver"], e["case"]) for e in MANIFEST}) == len(MANIFEST)


@pytest.mark.parametrize("entry", MANIFEST, ids=lambda e: e["file"])
def test_fixture_exists_and_holds_its_marker(entry: dict[str, object]) -> None:
    assert problems(entry, ROOT) == []


@pytest.mark.parametrize("entry", MANIFEST, ids=lambda e: e["file"])
def test_fixture_names_no_personal_path(entry: dict[str, object]) -> None:
    text = (ROOT / str(entry["file"])).read_bytes().decode("utf-8")
    assert PERSONAL.search(text) is None


def test_the_check_can_fail(tmp_path: Path) -> None:
    entry = next(e for e in MANIFEST if e["case"] == "unique_params")
    shutil.copytree(ROOT, tmp_path / "fx")
    root = tmp_path / "fx"
    target = root / str(entry["file"])
    target.write_bytes(target.read_bytes().replace(str(entry["marker"]).encode(), b"gone"))
    assert any("marker" in p for p in problems(entry, root))
    target.unlink()
    assert any("missing" in p for p in problems(entry, root))
    assert problems({"case": "x"}, root) != []
