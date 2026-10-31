"""Alembic history from files (F6, spec §7.6): ini, ``[tool.alembic]``, ``ast`` reads; never imports anything.

Derived cases (BootUI reads Flyway through its API; Alembic files have no BootUI oracle). No SQLAlchemy here: the
file side must work without it (ruling C4), so this module runs in the no-sqlalchemy job too.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
import types
from pathlib import Path

import pytest

from sharpit.engine.collectors.alembic import AlembicFiles, read_alembic_files
from sharpit.engine.masking import MASK, Exposure, Masker

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "alembic"
ROOT = Path(__file__).resolve().parents[2]
MASKER = Masker(Exposure.MASKED, True)
SECRET = "hunter2"


def _revs(files: AlembicFiles) -> list[tuple[str, tuple[str, ...]]]:
    return [(r.revision, r.down_revisions) for r in files.revisions]


def test_linear_history():
    files = read_alembic_files(FIXTURES / "linear" / "alembic.ini", MASKER)
    assert files.reason is None
    assert files.table_error is None
    assert _revs(files) == [("a1", ()), ("b2", ("a1",)), ("c3", ("b2",))]
    assert files.heads == ["c3"]
    first = files.revisions[0]
    assert (first.description, first.script) == ("create owners", "migrations/versions/a1_create_owners.py")
    assert (files.version_table, files.version_table_schema) == ("alembic_version", None)


def test_branch_and_merge_heads():
    files = read_alembic_files(FIXTURES / "branch_merge" / "alembic.ini", MASKER)
    order = [r.revision for r in files.revisions]
    assert order == ["base", "left", "right", "merge", "side", "tip"]
    assert files.heads == ["side", "tip"]
    assert dict(_revs(files))["merge"] == ("left", "right")


def test_modern_template_annassign():
    files = read_alembic_files(FIXTURES / "modern_template" / "alembic.ini", MASKER)
    assert _revs(files) == [("1f2e3d4c5b6a", ()), ("9a8b7c6d5e4f", ("1f2e3d4c5b6a",))]
    assert files.revisions[0].description == "initial schema"
    assert (files.version_table, files.version_table_schema) == ("schema_history", "app")


def test_revision_raising_at_import_still_parses():
    # c3_add_visits.py raises at module level: ast reads it, nothing executes it (env.py raises too)
    files = read_alembic_files(FIXTURES / "linear" / "alembic.ini", MASKER)
    assert "c3" in [r.revision for r in files.revisions]
    assert files.skipped == []


def test_package_dir_unimported_unresolved_not_imported():
    files = read_alembic_files(FIXTURES / "package_dir" / "alembic.ini", MASKER)
    assert files.reason is not None
    assert "unresolved" in files.reason
    assert "not imported" in files.reason
    assert "sharpit_alembic_fixture_pkg" not in sys.modules  # its __init__ raises: importing it would fail the test


def test_package_dir_resolved_through_an_imported_package(monkeypatch: pytest.MonkeyPatch):
    package = types.ModuleType("sharpit_alembic_fixture_pkg")
    package.__path__ = [str(FIXTURES / "package_dir" / "sharpit_alembic_fixture_pkg")]
    monkeypatch.setitem(sys.modules, "sharpit_alembic_fixture_pkg", package)
    files = read_alembic_files(FIXTURES / "package_dir" / "alembic.ini", MASKER)
    assert files.reason is None
    assert [r.revision for r in files.revisions] == ["p1"]


def test_pyproject_tool_alembic(tmp_path: Path):
    shutil.copytree(FIXTURES / "linear" / "migrations", tmp_path / "db")
    (tmp_path / "pyproject.toml").write_text('[tool.alembic]\nscript_location = "%(here)s/db"\n', "utf-8")
    files = read_alembic_files(tmp_path / "alembic.ini", MASKER)  # no ini: [tool.alembic] next to where it would be
    assert files.reason is None
    assert files.config_path == str(tmp_path / "pyproject.toml")
    assert files.heads == ["c3"]


def test_version_locations_with_separator(tmp_path: Path):
    shutil.copytree(FIXTURES / "linear" / "migrations" / "versions", tmp_path / "one")
    shutil.copytree(FIXTURES / "broken" / "migrations" / "versions", tmp_path / "two")
    (tmp_path / "alembic.ini").write_text(
        "[alembic]\nscript_location = %(here)s\npath_separator = ;\nversion_locations = %(here)s/one;%(here)s/two\n",
        "utf-8",
    )
    files = read_alembic_files(tmp_path / "alembic.ini", MASKER)
    assert sorted(r.revision for r in files.revisions) == ["a1", "b2", "c3", "ok1"]


def test_alembic_never_imported():
    code = textwrap.dedent(
        f"""
        import sys
        from pathlib import Path
        from sharpit.engine.collectors.alembic import read_alembic_files
        from sharpit.engine.masking import Exposure, Masker
        files = read_alembic_files(Path({str(FIXTURES / "linear" / "alembic.ini")!r}), Masker(Exposure.MASKED, True))
        assert files.heads == ["c3"], files
        print(sorted(m for m in ("alembic", "sqlalchemy") if m in sys.modules))
        """
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT, check=True)
    assert out.stdout.strip() == "[]", out.stderr


@pytest.mark.parametrize(
    ("option", "value"),
    [("version_table", "alembic_version; DROP TABLE owners"), ("version_table", "x" * 64), ("version_table", "1abc")],
)
def test_hostile_version_table_refused(tmp_path: Path, option: str, value: str):
    shutil.copytree(FIXTURES / "linear" / "migrations", tmp_path / "migrations")
    (tmp_path / "alembic.ini").write_text(f"[alembic]\nscript_location = %(here)s/migrations\n{option} = {value}\n")
    files = read_alembic_files(tmp_path / "alembic.ini", MASKER)
    assert files.table_error is not None
    assert option in files.table_error
    assert files.reason is None
    assert files.heads == ["c3"]


def test_hostile_version_table_schema_refused(tmp_path: Path):
    shutil.copytree(FIXTURES / "linear" / "migrations", tmp_path / "migrations")
    (tmp_path / "alembic.ini").write_text(
        "[alembic]\nscript_location = %(here)s/migrations\nversion_table_schema = public.x\n"
    )
    files = read_alembic_files(tmp_path / "alembic.ini", MASKER)
    assert files.table_error is not None
    assert "version_table_schema" in files.table_error


def test_large_and_unparsable_revision_skipped_with_reason(tmp_path: Path):
    shutil.copytree(FIXTURES / "broken", tmp_path / "broken")
    versions = tmp_path / "broken" / "migrations" / "versions"
    (versions / "bad_syntax.py").write_text('revision = "bad"\ndef broken(:\n', "utf-8")
    (versions / "huge.py").write_text('revision = "huge"\n' + "#" * (1024 * 1024), "utf-8")
    (versions / "computed.py").write_text('revision = "x" + "y"\n', "utf-8")
    files = read_alembic_files(tmp_path / "broken" / "alembic.ini", MASKER)
    assert [r.revision for r in files.revisions] == ["ok1"]  # not_a_revision.py has no revision: not listed
    reasons = dict(files.skipped)
    assert reasons["migrations/versions/huge.py"] == "larger than 1 MB"
    assert reasons["migrations/versions/bad_syntax.py"].startswith("cannot be parsed: SyntaxError")
    assert reasons["migrations/versions/computed.py"] == "revision is not a literal value"
    assert "migrations/versions/not_a_revision.py" not in reasons


@pytest.mark.parametrize(
    "ini",
    [
        f"sqlalchemy.url = postgresql://app:{SECRET}@db/app\n[alembic]\n",  # no section header: quotes the line
        f"[alembic]\nscript_location = %(here)s\nsqlalchemy.url = postgresql://app:{SECRET}@db/app\n  bad\n[x\n",
    ],
    ids=["missing-section-header", "parsing-error"],
)
def test_ini_error_masked(tmp_path: Path, ini: str):
    (tmp_path / "alembic.ini").write_text(ini, "utf-8")
    files = read_alembic_files(tmp_path / "alembic.ini", MASKER)
    assert files.reason is not None
    assert files.reason.startswith("Cannot read")
    assert SECRET not in files.reason


def test_ini_error_metadata_only_is_generic(tmp_path: Path):
    (tmp_path / "alembic.ini").write_text(f"sqlalchemy.url = postgresql://app:{SECRET}@db/app\n", "utf-8")
    files = read_alembic_files(tmp_path / "alembic.ini", Masker(Exposure.METADATA_ONLY, True))
    assert files.reason == f"Cannot read {tmp_path / 'alembic.ini'}"


def test_alembic_docstring_masked(tmp_path: Path):
    versions = tmp_path / "migrations" / "versions"
    versions.mkdir(parents=True)
    (tmp_path / "alembic.ini").write_text("[alembic]\nscript_location = %(here)s/migrations\n", "utf-8")
    (versions / "r1.py").write_text(f'"""rotate password={SECRET} for app"""\n\nrevision = "r1"\n', "utf-8")
    files = read_alembic_files(tmp_path / "alembic.ini", MASKER)
    assert files.revisions[0].description == f"rotate password={MASK} for app"


def test_no_ini_unavailable(tmp_path: Path):
    files = read_alembic_files(tmp_path / "alembic.ini", MASKER)
    assert files.reason is not None
    assert files.reason.startswith("No Alembic configuration")
    assert files.revisions == []
