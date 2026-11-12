"""Alembic panel (F6, spec §7.6): the migration history from files, the database version on request only.

Alembic is never imported and ``env.py`` never runs: the ini is read with ``configparser`` (or ``[tool.alembic]`` with
``tomllib``) and each revision file with ``ast``, so nothing executes and no ``__pycache__`` is written. The database
side (``SELECT version_num``) connects, so it runs only on ``POST {api}/alembic/refresh`` and is cached.
"""

from __future__ import annotations

import ast
import configparser
import functools
import heapq
import importlib.util
import os
import re
import sys
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from sharpit.engine import sqla
from sharpit.engine.daemon_executor import DaemonExecutor
from sharpit.engine.singleflight import ActionBusy, Flight, SingleFlight
from sharpit.engine.sqltext import Dialect, dialect_of_name, error_text

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext
    from sharpit.engine.masking import Masker

OPERATION = "alembic-refresh"
NOT_READ = "(not read yet)"
NEVER_RUNS = "sharpit never runs migrations"  # the clean action's reason until W8 M2
MIGRATE_OPERATION = "alembic-migrate"
ACTION_FLIGHT = "singleflight:alembic-actions"  # one lock for migrate and (M2) clean
CONFIRMATION_REQUIRED = "Action requires confirm=true because it mutates the application database."
NO_TARGET = "No Alembic configuration matched the requested database."
NOT_INSTALLED = "Alembic is not installed in this Python environment"
_UPGRADE_LINE = re.compile(r"\bRunning upgrade\b")
_LOGGER_NAME = "alembic.runtime.migration"
NOT_SET = "No Alembic configuration: SHARPIT_ALEMBIC_CONFIG is not set"
NO_ENGINE = "No database engine is registered yet: pass engines=[...] to install(), or let the app run a query first"
MAX_REVISION_BYTES = 1024 * 1024
MAX_ERROR_BYTES = 4096
DEFAULT_VERSION_TABLE = "alembic_version"
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}")
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")
_SEPARATORS = {"os": os.pathsep, ":": ":", ";": ";", "space": " ", "newline": "\n"}
_VARIABLES = ("revision", "down_revision", "branch_labels", "depends_on")
_OPTIONS = (
    "script_location",
    "version_locations",
    "path_separator",
    "version_path_separator",
    "version_table",
    "version_table_schema",
)


@dataclass(frozen=True)
class Revision:
    revision: str
    down_revisions: tuple[str, ...]
    description: str | None
    script: str  # relative to the config file's directory, with forward slashes


@dataclass
class AlembicFiles:
    config_path: str
    reason: str | None = None  # why there is no history: config missing, unreadable or unresolved
    version_table: str = DEFAULT_VERSION_TABLE
    version_table_schema: str | None = None
    table_error: str | None = None  # a hostile version_table / version_table_schema: the database read is refused
    version_dirs: list[Path] = field(default_factory=list[Path])
    revisions: list[Revision] = field(default_factory=list[Revision])  # oldest first
    heads: list[str] = field(default_factory=list[str])
    skipped: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])  # (script, reason)


@dataclass(frozen=True)
class DatabaseRead:
    name: str
    heads: tuple[str, ...] | None  # None: not read (reason says why)
    reason: str | None
    checked_at: int


class AlembicState:
    """The cached database reads of the last refresh (``None`` before the first one)."""

    def __init__(self) -> None:
        self.reads: list[DatabaseRead] | None = None


# --- files ----------------------------------------------------------------------------------------------------------


def _error(masker: Masker, path: Path, exc: BaseException) -> str:
    # a configparser error can quote the line it failed on, sqlalchemy.url included
    return masker.mask_text(f"Cannot read {path}: {type(exc).__name__}: {exc}") or f"Cannot read {path}"


def _config(ini_path: Path, masker: Masker) -> tuple[AlembicFiles, dict[str, Any], Path]:
    """The config file found (ini, else ``[tool.alembic]`` in the pyproject.toml next to it) and its options."""
    if ini_path.is_file():
        here = ini_path.resolve().parent
        parser = configparser.ConfigParser(defaults={"here": str(here)})
        try:
            parser.read_string(ini_path.read_text("utf-8"), source=str(ini_path))
            if not parser.has_section("alembic"):
                return AlembicFiles(str(ini_path), f"{ini_path} has no [alembic] section"), {}, here
            options = {k: parser.get("alembic", k) for k in _OPTIONS if parser.has_option("alembic", k)}
        except (configparser.Error, OSError, UnicodeDecodeError) as exc:
            return AlembicFiles(str(ini_path), _error(masker, ini_path, exc)), {}, here
        return AlembicFiles(str(ini_path)), options, here
    pyproject = ini_path.parent / "pyproject.toml"
    missing = f"No Alembic configuration: {ini_path} not found and no [tool.alembic] in {pyproject}"
    if not pyproject.is_file():
        return AlembicFiles(str(ini_path), missing), {}, ini_path.parent
    here = pyproject.resolve().parent
    try:
        data = tomllib.loads(pyproject.read_text("utf-8"))
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as exc:
        return AlembicFiles(str(pyproject), _error(masker, pyproject, exc)), {}, here
    tool = data.get("tool")
    table = cast("dict[str, Any]", tool).get("alembic") if isinstance(tool, dict) else None
    if not isinstance(table, dict):
        return AlembicFiles(str(ini_path), missing), {}, here
    options = {k: v for k, v in cast("dict[str, Any]", table).items() if k in _OPTIONS}
    options = {k: v.replace("%(here)s", str(here)) if isinstance(v, str) else v for k, v in options.items()}
    return AlembicFiles(str(pyproject)), options, here


def _location(value: str) -> Path | str:
    """A directory, or why ``package:dir`` is unresolved (only an already imported package is used)."""
    if ":" in value and not Path(value).is_absolute() and not _DRIVE.match(value):
        package, _, sub = value.partition(":")
        paths = getattr(sys.modules.get(package), "__path__", None)
        if not paths:
            return (
                f"script location {value!r} is unresolved: package {package!r} is not imported yet "
                "(sharpit never imports it)"
            )
        return Path(next(iter(cast("list[str]", paths)))) / sub
    return Path(value)  # relative to the working directory, as Alembic does


def _split(raw: object, separator: object) -> list[str]:
    if isinstance(raw, list):
        return [str(item) for item in cast("list[object]", raw)]
    text = str(raw)
    if isinstance(separator, str) and separator in _SEPARATORS:
        return [part.strip() for part in text.split(_SEPARATORS[separator]) if part.strip()]
    return [part for part in re.split(r", *|(?: +)", text.strip()) if part]  # Alembic's legacy split


def _relative(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def _literal(value: ast.expr) -> object:
    return ast.literal_eval(value)


def _parse_revision(path: Path, base: Path, masker: Masker) -> Revision | str | None:
    """The revision in ``path``, a reason it was skipped, or None when the file declares no ``revision``."""
    try:
        if path.stat().st_size > MAX_REVISION_BYTES:
            return "larger than 1 MB"
        tree = ast.parse(path.read_bytes(), filename=path.name)
    except (OSError, SyntaxError, ValueError, MemoryError, RecursionError) as exc:
        return masker.mask_text(f"cannot be parsed: {type(exc).__name__}: {exc}") or "cannot be parsed"
    values: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:  # revision: str = "abc" (Alembic >= 1.12)
            targets, value = [node.target], node.value
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id in _VARIABLES:
                try:
                    values[target.id] = _literal(value)
                except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                    return f"{target.id} is not a literal value"
    if "revision" not in values:
        return None
    revision = values["revision"]
    if not isinstance(revision, str) or not revision:
        return "revision is not a non-empty string"
    down = values.get("down_revision")
    if isinstance(down, str):
        downs: tuple[str, ...] = (down,)
    elif isinstance(down, tuple | list):
        downs = tuple(d for d in cast("tuple[object, ...]", tuple(cast("Any", down))) if isinstance(d, str))
    else:
        downs = ()
    doc = ast.get_docstring(tree)
    first = doc.strip().splitlines()[0] if doc and doc.strip() else None
    return Revision(revision, downs, masker.mask_text(first), _relative(path, base))


def _order(revisions: dict[str, Revision]) -> list[Revision]:
    """Oldest first (bases first, each revision after its parents); ties broken by script path."""
    children: dict[str, list[str]] = {r: [] for r in revisions}
    waiting = dict.fromkeys(revisions, 0)
    for rev in revisions.values():
        for parent in rev.down_revisions:
            if parent in revisions:
                children[parent].append(rev.revision)
                waiting[rev.revision] += 1
    ready = [(revisions[r].script, r) for r, n in waiting.items() if n == 0]
    heapq.heapify(ready)
    ordered: list[Revision] = []
    while ready:
        _, rid = heapq.heappop(ready)
        ordered.append(revisions[rid])
        for child in children[rid]:
            waiting[child] -= 1
            if waiting[child] == 0:
                heapq.heappush(ready, (revisions[child].script, child))
    seen = {r.revision for r in ordered}
    return ordered + sorted((r for r in revisions.values() if r.revision not in seen), key=lambda r: r.script)


def read_alembic_files(ini_path: Path, masker: Masker) -> AlembicFiles:
    """The history in the files next to ``ini_path``; never imports Alembic or the revision modules."""
    files, options, here = _config(ini_path, masker)
    if files.reason is not None:
        return files
    files.version_table = str(options.get("version_table") or DEFAULT_VERSION_TABLE)
    schema = options.get("version_table_schema")
    files.version_table_schema = str(schema) if schema else None
    for label, value in (("version_table", files.version_table), ("version_table_schema", files.version_table_schema)):
        if value is not None and not _IDENTIFIER.fullmatch(value):
            shown = masker.mask_text(value) or ""
            files.table_error = f"Refused to read the database: {label} {shown!r} is not a plain identifier"
    script_location = options.get("script_location")
    if not script_location:
        files.reason = f"{files.config_path} sets no script_location"
        return files
    script_dir = _location(str(script_location))
    if isinstance(script_dir, str):
        files.reason = script_dir
        return files
    raw = options.get("version_locations")
    separator = options.get("path_separator") or options.get("version_path_separator")
    for item in _split(raw, separator) if raw else []:
        location = _location(item)
        if isinstance(location, str):
            files.skipped.append((item, location))
        else:
            files.version_dirs.append(location)
    if not raw:
        files.version_dirs.append(script_dir / "versions")
    found: dict[str, Revision] = {}
    for directory in files.version_dirs:
        for path in sorted(directory.glob("*.py")) if directory.is_dir() else []:
            parsed = _parse_revision(path, here, masker)
            if isinstance(parsed, str):
                files.skipped.append((_relative(path, here), parsed))
            elif parsed is not None and parsed.revision in found:
                files.skipped.append((parsed.script, f"duplicate revision {parsed.revision!r}"))
            elif parsed is not None:
                found[parsed.revision] = parsed
    files.revisions = _order(found)
    parents = {p for r in found.values() for p in r.down_revisions}
    files.heads = sorted(r for r in found if r not in parents)
    return files


def _ini_path(ctx: SharpitContext) -> Path | None:
    configured = ctx.settings.alembic_config
    return Path(configured) if configured else None


def _files(ctx: SharpitContext) -> AlembicFiles:
    path = _ini_path(ctx)
    return read_alembic_files(path, ctx.masker) if path is not None else AlembicFiles("", NOT_SET)


def unavailable_reason(ctx: SharpitContext) -> str | None:
    """Why the panel has nothing to show: no ini or ``[tool.alembic]`` found, or the config cannot be used."""
    path = _ini_path(ctx)
    if path is None:
        return NOT_SET
    files, options, _here = _config(path, ctx.masker)
    if files.reason is None and options.get("script_location"):
        location = _location(str(options["script_location"]))
        return location if isinstance(location, str) else None
    return files.reason or f"{files.config_path} sets no script_location"


# --- report ---------------------------------------------------------------------------------------------------------


def _row(rev: Revision | None, version: str, state: str) -> dict[str, Any]:
    return {
        "type": "PYTHON",
        "version": version,
        "description": rev.description if rev else None,
        "script": rev.script if rev else None,
        "state": state,
        "installedBy": None,
        "installedOn": None,
        "installedRank": None,
        "executionTime": None,
        "checksum": None,
    }


def _applied(files: AlembicFiles, heads: tuple[str, ...]) -> set[str]:
    by_id = {r.revision: r for r in files.revisions}
    applied: set[str] = set()
    todo = [h for h in heads if h in by_id]
    while todo:
        rid = todo.pop()
        if rid not in applied:
            applied.add(rid)
            todo.extend(p for p in by_id[rid].down_revisions if p in by_id)
    return applied


def _database(
    files: AlembicFiles, name: str, read: DatabaseRead | None, reason: str | None, migrate_reason: str | None
) -> dict[str, Any]:
    heads = read.heads if read else None
    if heads is None:
        rows = [_row(r, r.revision, "Unknown") for r in files.revisions]
    else:
        applied = _applied(files, heads)
        known = {r.revision for r in files.revisions}
        rows = [_row(r, r.revision, "Success" if r.revision in applied else "Pending") for r in files.revisions]
        rows += [_row(None, h, "Missing") for h in heads if h not in known]
    return {
        "name": name,
        "currentVersion": ",".join(heads) if heads else None,
        "applied": sum(r["state"] in ("Success", "Missing") for r in rows),
        "pending": sum(r["state"] == "Pending" for r in rows),
        "total": len(rows),
        "migrations": rows,
        "migrateEnabled": migrate_reason is None,
        "migrateDisabledReason": migrate_reason,
        "cleanEnabled": False,
        "cleanDisabledReason": NEVER_RUNS,
        "checkedAt": read.checked_at if read else None,
        "unavailableReason": read.reason if read else reason,
    }


def _report(ctx: SharpitContext, files: AlembicFiles) -> dict[str, Any]:
    if files.reason is not None:
        return {"alembicPresent": False, "configPath": files.config_path, "total": 0, "heads": [], "databases": []}
    state = ctx.peek("alembic")
    reads = state.reads if isinstance(state, AlembicState) else None
    registry = ctx.capture.engine_registry
    engines = registry.names() if registry is not None else []
    migrate_reason = _migrate_reason(ctx, bool(engines))
    if reads:
        databases = [_database(files, r.name, r, None, migrate_reason) for r in reads]
    else:
        databases = [_database(files, NOT_READ, None, None if engines else NO_ENGINE, migrate_reason)]
    return {
        "alembicPresent": True,
        "configPath": files.config_path,
        "total": len(files.revisions),
        "heads": files.heads,
        "databases": databases,
    }


def alembic_report(ctx: SharpitContext) -> dict[str, Any]:
    """``{alembicPresent, configPath, total, heads, databases}``: the files plus the cached database read.

    Never connects: the database is read only by ``refresh_alembic``.
    """
    return _report(ctx, _files(ctx))


# --- database read (POST only) --------------------------------------------------------------------------------------


def _versions(table: str, schema: str | None, conn: Any) -> list[str] | None:
    """``version_num`` rows, or None when the database has no version table (not managed by Alembic)."""
    if not conn.dialect.has_table(conn, table, schema=schema):
        return None
    prep = conn.dialect.identifier_preparer
    name = prep.quote(table) if schema is None else f"{prep.quote_schema(schema)}.{prep.quote(table)}"
    # name comes from the dialect's identifier preparer, so it is quoted
    return [str(row[0]) for row in conn.exec_driver_sql(f"SELECT version_num FROM {name}")]  # noqa: S608


async def _read(
    ctx: SharpitContext, files: AlembicFiles, name: str, engine: Any, flight: Flight, executor: DaemonExecutor
) -> DatabaseRead:
    checked = int(time.time() * 1000)
    if files.table_error is not None:
        return DatabaseRead(name, None, files.table_error, checked)
    timeout = ctx.settings.alembic_timeout
    read = functools.partial(_versions, files.version_table, files.version_table_schema)
    try:
        heads = await sqla.run_db_read(engine, read, timeout, executor=executor, done=flight.worker())
    except TimeoutError:
        return DatabaseRead(name, None, f"Reading the database version timed out after {timeout:g}s", checked)
    except sqla.ReadOnlyUnavailable as exc:
        return DatabaseRead(name, None, exc.reason, checked)
    except Exception as exc:  # noqa: BLE001 - a failed read is reported for that database, never raised
        dialect = dialect_of_name(getattr(getattr(engine, "dialect", None), "name", None)) or Dialect.UNSUPPORTED
        reason = error_text(ctx.masker, exc, dialect) or type(exc).__name__
        return DatabaseRead(name, None, reason, checked)
    if heads is None:
        table = (
            files.version_table
            if files.version_table_schema is None
            else (f"{files.version_table_schema}.{files.version_table}")
        )
        return DatabaseRead(name, None, f"Not managed by Alembic: no {table} table", checked)
    return DatabaseRead(name, tuple(heads), None, checked)


async def refresh_alembic(ctx: SharpitContext) -> dict[str, Any]:
    """Read each registered engine's version table (single-flight, held until every worker thread returns)."""
    single = ctx.lazy(f"singleflight:{OPERATION}", SingleFlight)
    release = single.try_acquire(OPERATION)
    if release is None:
        raise ActionBusy(OPERATION, single.active)
    flight = Flight(release)
    try:
        files = _files(ctx)
        if files.reason is not None:
            return _report(ctx, files)
        registry = ctx.capture.engine_registry
        engines = registry.engines() if registry is not None else []
        executor = ctx.lazy("alembic.executor", lambda: DaemonExecutor(2, thread_name_prefix="sharpit-alembic"))
        reads = [await _read(ctx, files, name, engine, flight, executor) for name, engine in engines]
        ctx.lazy("alembic", AlembicState).reads = reads
        return _report(ctx, files)
    finally:
        flight.done()


# --- migrate (POST only; the child process is started by ``alembic_cli`` and passed in as ``run``) ------------------


class ProcessResult(Protocol):
    @property
    def returncode(self) -> int | None: ...
    @property
    def output(self) -> str: ...
    @property
    def failure(self) -> str | None: ...


Runner = Callable[[list[str], str], ProcessResult]


def _installed() -> bool:
    try:
        return importlib.util.find_spec("alembic") is not None  # a spec lookup: nothing is imported
    except (ImportError, ValueError):
        return False


def _ini_file(ctx: SharpitContext) -> Path | None:
    path = _ini_path(ctx)
    return Path(os.path.abspath(path)) if path is not None and path.is_file() else None


def _migrate_reason(ctx: SharpitContext, has_engines: bool) -> str | None:
    """Why migrate is off for the report, or None when the action can run."""
    if not _installed():
        return NOT_INSTALLED
    if _ini_file(ctx) is None:
        return f"Alembic migrate needs the config file {ctx.settings.alembic_config}"
    return None if has_engines else NO_ENGINE


def _section(ini: Path, target: str) -> str | None:
    """``-n <target>`` only when the ini has a plain-identifier section of that name (a multi-database project)."""
    if target == "alembic" or not _IDENTIFIER.fullmatch(target):
        return None
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read_string(ini.read_text("utf-8"))
    except (configparser.Error, OSError, UnicodeDecodeError):
        return None
    return target if parser.has_section(target) else None


def _answer(status: int, result: str, message: str, name: str | None, executed: int | None = None) -> tuple[int, Any]:
    return status, {
        "status": result,
        "message": message,
        "beanName": name,
        "migrationsExecuted": executed,
        "schemasCleaned": [],
        "schemasDropped": [],
        "migrationPath": None,
        "warnings": [],
    }


def _capped(ctx: SharpitContext, text: str | None) -> str:
    """Masked first (a secret is never cut in half), then the last ``MAX_ERROR_BYTES`` bytes."""
    masked = ctx.masker.mask_text(text) or ""
    return masked.encode("utf-8")[-MAX_ERROR_BYTES:].decode("utf-8", "ignore").strip()


def _executed(output: str) -> int | None:
    """Revisions applied, from Alembic's own ``Running upgrade`` log lines; None when its logging is off."""
    count = len(_UPGRADE_LINE.findall(output))
    return count if count or _LOGGER_NAME in output else None


def _failure(ctx: SharpitContext, result: ProcessResult) -> str:
    if result.failure == "timeout":
        return "Alembic did not finish in time and was stopped."
    text = _capped(ctx, result.output)
    if text:
        return text
    return f"Alembic failed with exit code {result.returncode}." if result.failure is None else "Alembic did not run."


def _upgrade(ctx: SharpitContext, ini: Path, target: str, run: Runner) -> tuple[int, Any]:
    section = _section(ini, target)
    argv = [sys.executable, "-m", "alembic", "-c", str(ini), *(["-n", section] if section else []), "upgrade", "heads"]
    try:
        result = run(argv, str(ini.parent))
    except Exception as exc:  # noqa: BLE001 - the action answers 500; SingleFlight.run releases the lock
        return _answer(500, "failed", _capped(ctx, f"{type(exc).__name__}: {exc}") or "Alembic did not run.", target)
    if result.failure is not None or result.returncode != 0:
        return _answer(500, "failed", _failure(ctx, result), target)
    executed = _executed(result.output)
    if executed is None:
        message = "Alembic upgrade completed."
    elif executed == 0:
        message = "Alembic schema is already up to date."
    else:
        message = f"Alembic applied {executed} migration(s)."
    return _answer(200, "success", message, target, executed)


def migrate(ctx: SharpitContext, body: dict[str, Any], run: Runner) -> tuple[int, Any]:
    """``FlywayService.migrate``: blocked, target, confirmation, single-flight, then run. Returns (status, DTO).

    The target is one of the engine names sharpit itself reports, never the request string; the argv holds no request
    text. ``confirm`` must be JSON ``true`` exactly.
    """
    given = body.get("beanName")
    requested = given if isinstance(given, str) and given.strip() else None
    if not _installed():
        return _answer(403, "blocked", NOT_INSTALLED, requested)
    registry = ctx.capture.engine_registry
    targets = registry.names() if registry is not None else []
    ini = _ini_file(ctx)
    if requested is None:
        target = targets[0] if len(targets) == 1 else None
    else:
        target = requested if requested in targets else None
    if ini is None or target is None:
        return _answer(404, "unavailable", NO_TARGET, None)
    if body.get("confirm") is not True:
        return _answer(400, "blocked", CONFIRMATION_REQUIRED, target)
    single = ctx.lazy(ACTION_FLIGHT, SingleFlight)
    return single.run(MIGRATE_OPERATION, lambda: _upgrade(ctx, ini, target, run))
