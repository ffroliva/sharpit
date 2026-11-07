"""A10: wired surfaces must resolve their proven database family."""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from tests.masking.a10.conftest import a10_surface, fixture_rows, plant_fails, scratch_package

from sharpit.engine import sqltext
from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqla.dialect_source import EngineDialectSource, ExceptionDialectSource
from sharpit.engine.sqltext import Dialect, DialectContext, resolve

pytestmark = pytest.mark.needs_sqlalchemy
ROOT = Path(__file__).resolve().parents[3]
FAMILY_TEST = "tests/masking/a10/test_gate.py::test_every_fixture_type_resolves_to_its_family"


def test_the_facade_has_all_three_entries() -> None:
    assert callable(getattr(sqltext, "statement_text", None))
    assert callable(getattr(sqltext, "error_text", None))
    assert callable(getattr(sqltext, "statement_shape", None))


def test_statement_shape_uses_masked_text_for_its_fingerprint() -> None:
    masker = Masker(Exposure.MASKED, True, None)
    shape = sqltext.statement_shape(masker, "SELECT 'A10VALUE'", Dialect.SQLITE)
    assert shape.text == "SELECT ?"
    assert shape.fingerprint is None
    assert shape.dialect is Dialect.SQLITE
    assert shape.literal_count == 1


def test_metadata_only_shape_keeps_the_normalized_sql() -> None:
    masker = Masker(Exposure.METADATA_ONLY, True, None)
    shape = sqltext.statement_shape(masker, "SELECT 'A10VALUE'", Dialect.SQLITE)
    assert shape.text == "SELECT ?"
    assert shape.fingerprint is None


def test_error_text_accepts_the_facade_source_type() -> None:
    masker = Masker(Exposure.MASKED, True, None)
    assert sqltext.error_text(masker, "connection failed", Dialect.SQLITE) == "connection failed"


def test_statement_text_keeps_a_known_word() -> None:
    text = sqltext.statement_text(Masker(Exposure.MASKED, True), "SELECT 'A10VALUE' FROM a10", Dialect.SQLITE)
    assert text is not None
    assert "SELECT" in text


def test_error_text_keeps_a_known_word_in_errors() -> None:
    error = RuntimeError("(sqlite3.OperationalError) failed\n[SQL: SELECT 'A10VALUE' FROM a10]")
    text = sqltext.error_text(Masker(Exposure.MASKED, True), error, Dialect.SQLITE)
    assert text is not None
    assert "SQL" in text


def test_conflicting_exception_chain_is_unsupported() -> None:
    sqlite = type("SqliteFailure", (Exception,), {"__module__": "sqlite3"})()
    postgres = type("PostgresFailure", (Exception,), {"__module__": "psycopg.errors"})()
    postgres.__cause__ = sqlite
    assert resolve(postgres, (ExceptionDialectSource(),), DialectContext(lambda: None)) is Dialect.UNSUPPORTED


def test_conflicting_sources_are_unsupported() -> None:
    class Source:
        def __init__(self, family: Dialect) -> None:
            self.family = family

        def dialect_of(self, _event: object, _context: DialectContext) -> Dialect:
            return self.family

    result = resolve(object(), (Source(Dialect.SQLITE), Source(Dialect.POSTGRESQL)), DialectContext(lambda: None))
    assert result is Dialect.UNSUPPORTED


def test_application_conflict_is_unsupported() -> None:
    error = type("SqliteFailure", (Exception,), {"__module__": "sqlite3"})()
    result = resolve(error, (ExceptionDialectSource(),), DialectContext(lambda: Dialect.POSTGRESQL))
    assert result is Dialect.UNSUPPORTED


def test_application_family_resolves_when_no_source_proves_one() -> None:
    result = resolve(object(), (ExceptionDialectSource(),), DialectContext(lambda: Dialect.SQLITE))
    assert result is Dialect.SQLITE


def test_every_fixture_type_resolves_to_its_family() -> None:
    rows = fixture_rows()
    assert len(rows) == 164
    if os.environ.get("SHARPIT_A10_SQLITE_ONLY"):
        rows = [row for row in rows if row[1] is Dialect.SQLITE]
    families = {family for _, family, _, _ in rows}
    assert families >= {Dialect.SQLITE, Dialect.POSTGRESQL, Dialect.MYSQL_FAMILY}
    source = ExceptionDialectSource()
    report = a10_surface(
        "fixture-types",
        lambda: (
            (
                "source_chain",
                family,
                resolve(error, (source,), DialectContext(lambda: None)),
                sqltext.error_text(Masker(Exposure.MASKED, True), error, family) or type(error).__name__,
                next(word for word in re.findall(r"[A-Za-z]+", raw) if len(word) > 2),
            )
            for _, family, error, raw in rows
        ),
    )
    assert report.counts["source_chain"] == len(rows)


# derived: Task 27 review 2 (fixture_rows populate orig.args with the driver message text)
def test_fixture_rows_carry_driver_message_args() -> None:
    for file, _family, error, raw in fixture_rows():
        orig = getattr(error, "orig", None)
        assert isinstance(orig, BaseException), file
        args = BaseException.args.__get__(orig)
        assert any(type(v) is str and bool(v) for v in args), file
        if getattr(error, "statement", None) is None:
            known_word = next(word for word in re.findall(r"[A-Za-z]+", raw) if len(word) > 2)
            assert known_word in args[0], file


def test_the_recorder_uses_the_sqlite_engine_family() -> None:
    engine = sa.create_engine("sqlite://")
    try:
        event = SimpleNamespace(dialect=engine.dialect, engine=engine, error=None)
        resolved = resolve(event, (EngineDialectSource(),), DialectContext(lambda: None))
        recorder = SqlTraceRecorder(Masker(Exposure.MASKED, True, None), capture_call_site=False)
        recorder.record("SELECT 'A10VALUE'", duration_ns=1, thread="t", connection_id=None, dialect=resolved)
        row = recorder.rows()[0]
        assert row["shape"].dialect is Dialect.SQLITE
    finally:
        engine.dispose()


def test_a_build_without_the_chain_walk_fails_a10(tmp_path: Path) -> None:
    copy = scratch_package(tmp_path)
    plant_fails(
        copy, FAMILY_TEST, "engine/sqla/dialect_source.py", "reading = read_chain(error)", "return Dialect.UNSUPPORTED"
    )


def test_a_build_that_resolves_nothing_fails_a10(tmp_path: Path) -> None:
    copy = scratch_package(tmp_path)
    plant_fails(
        copy,
        FAMILY_TEST,
        "engine/sqltext/dialect.py",
        "        proof: set[Dialect] = set()",
        "        return Dialect.UNSUPPORTED\n        proof: set[Dialect] = set()",
    )


def test_a_build_that_hides_every_statement_fails_a10(tmp_path: Path) -> None:
    copy = scratch_package(tmp_path)
    plant_fails(
        copy,
        "tests/masking/a10/test_gate.py::test_statement_text_keeps_a_known_word",
        "engine/sqltext/__init__.py",
        "return _statement_text(masker, sql, LEXER.scan(sql, dialect))",
        "return MASK",
    )


def test_a_build_that_hides_every_error_fails_a10(tmp_path: Path) -> None:
    copy = scratch_package(tmp_path)
    plant_fails(
        copy,
        "tests/masking/a10/test_gate.py::test_error_text_keeps_a_known_word_in_errors",
        "engine/sqltext/__init__.py",
        "return render_error_text(masker, source, dialect, known, keep_frames)",
        "return MASK",
    )


def test_a_sqlite_only_input_is_refused(tmp_path: Path) -> None:
    copy = scratch_package(tmp_path)
    # Restricting the fixture corpus models a SQLite-only run; the same A10 row must reject it.
    env = os.environ.copy()
    env["SHARPIT_A10_SQLITE_ONLY"] = "1"
    env["PYTHONPATH"] = os.pathsep.join((str(copy.parent), str(ROOT), env.get("PYTHONPATH", "")))
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", FAMILY_TEST],
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


# --- every surface is wired (Task 28) ---------------------------------------------------------------------------------
# derived: architecture plan Task 28: a surface reads through the facade, ``sharpit.engine.sqltext``; the forwarding
# modules keep the old names working for tests until Task 30, and no module in the package may still reach them.
FORWARDERS = {
    "sharpit.engine.capture.sqlscan": None,  # every name
    "sharpit.engine.capture.statement": None,
    "sharpit.engine.capture.errortext": None,
    "sharpit.engine.capture.sqltrace": {"Normalized", "mask_error", "normalize", "normalize_sql"},  # its re-exports
}
PACKAGE = Path(sqltext.__file__).resolve().parents[2]
FORWARDER_FILES = {f"engine/capture/{name}.py" for name in ("sqlscan", "statement", "errortext")}
SURFACE_MODULES = sorted(
    path.relative_to(PACKAGE).as_posix()
    for path in PACKAGE.rglob("*.py")
    if path.relative_to(PACKAGE).as_posix() not in FORWARDER_FILES
)


def _forwards(module: str, name: str) -> bool:
    names = FORWARDERS.get(module, set())
    return names is None or name in names


def _imported_module(node: ast.ImportFrom, surface: str) -> str:
    """The absolute module of ``from X import ...``, a relative ``X`` resolved against ``surface``'s package."""
    if not node.level:
        return node.module or ""
    # ``engine/x/y.py`` is in ``sharpit.engine.x``; ``engine/x/__init__.py`` is ``sharpit.engine.x`` itself
    package = ["sharpit", *surface.removesuffix(".py").split("/")][:-1]
    base = package[: len(package) - (node.level - 1)]
    return ".".join([*base, node.module] if node.module else base)


def _forwarding_uses(tree: ast.Module, surface: str) -> list[str]:
    """Each load of a name bound to a forwarder, or of a forwarded attribute of a forwarding module, by line.

    Imports are read as written: aliased, dotted (``import a.b`` then ``a.b.f``) and relative. A lookup by
    ``importlib`` or ``getattr`` with a computed name is out of scope: no static read can follow it.
    """
    names: set[str] = set()
    modules: dict[str, str] = {}  # the dotted text a module is reached by -> the module
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = _imported_module(node, surface)
            for alias in node.names:
                if f"{module}.{alias.name}" in FORWARDERS:  # ``from sharpit.engine.capture import sqlscan``
                    modules[alias.asname or alias.name] = f"{module}.{alias.name}"
                elif _forwards(module, alias.name):
                    names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            modules.update({alias.asname or alias.name: alias.name for alias in node.names if alias.name in FORWARDERS})
    used = [
        f"{node.lineno}: {node.id}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in names
    ]
    used += [
        f"{node.lineno}: {ast.unparse(node)}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and ast.unparse(node.value) in modules
        and _forwards(modules[ast.unparse(node.value)], node.attr)
    ]
    return used


@pytest.mark.parametrize("surface", SURFACE_MODULES)
def test_every_surface_is_wired(surface: str) -> None:
    tree = ast.parse((PACKAGE / surface).read_text(encoding="utf-8"))
    assert _forwarding_uses(tree, surface) == []


def test_a_surface_calling_a_forwarder_fails_wiring(tmp_path: Path) -> None:
    anchor = '    return error_text(ctx.masker, text, dialect) or text.split(" (", 1)[0]'
    plant_fails(
        scratch_package(tmp_path),
        "tests/masking/a10/test_gate.py::test_every_surface_is_wired[engine/collectors/data.py]",
        "engine/collectors/data.py",
        anchor,
        "    from sharpit.engine.capture.sqltrace import mask_error\n\n" + anchor.replace("error_text", "mask_error"),
    )


# derived: Task 28 review F1: the gate read only aliased imports and absolute modules
DATA_ANCHOR = '    return error_text(ctx.masker, text, dialect) or text.split(" (", 1)[0]'
CALLED_OLD = DATA_ANCHOR.replace("error_text(", "{}(")
FORWARDER_FORMS = {
    "dotted": "    import sharpit.engine.capture.sqltrace\n\n"
    + CALLED_OLD.format("sharpit.engine.capture.sqltrace.mask_error"),
    "relative_name": "    from ..capture.sqltrace import mask_error\n\n" + CALLED_OLD.format("mask_error"),
    "relative_module": "    from ..capture import errortext\n\n" + CALLED_OLD.format("errortext.mask_error"),
}


@pytest.mark.parametrize("form", FORWARDER_FORMS)
def test_a_forwarder_reached_by_another_import_form_fails_wiring(form: str, tmp_path: Path) -> None:
    plant_fails(
        scratch_package(tmp_path),
        "tests/masking/a10/test_gate.py::test_every_surface_is_wired[engine/collectors/data.py]",
        "engine/collectors/data.py",
        DATA_ANCHOR,
        FORWARDER_FORMS[form],
    )
