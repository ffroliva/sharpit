"""Bounded, read-only index of the host application's source (spec §4.2). Never imports or executes it.

Every source reader resolves the app's root through ``resolve_package_root`` (module globals in ``sys.modules`` only)
and reads it through ``build_index``: ``os.scandir``, ``realpath`` + ``commonpath`` containment, ``S_ISREG`` before
opening, bounded files and bytes, parse errors recorded as limitations. Config's getenv scan lives here too.
"""

from __future__ import annotations

import ast
import io
import os
import stat
import threading
import time
import tokenize
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

MAX_FILES = 2000
MAX_FILE_BYTES = 524_288
_SKIP_DIRS = frozenset({".venv", "venv", "node_modules", "__pycache__", "site-packages"})
_READ_ERRORS = (OSError, SyntaxError, ValueError, LookupError, RecursionError, MemoryError)


@dataclass(frozen=True)
class ModuleInfo:
    name: str
    path: Path
    tree: ast.Module
    imports: tuple[str, ...]
    functions: tuple[str, ...]


@dataclass
class SourceIndex:
    modules: dict[str, ModuleInfo] = field(default_factory=dict[str, ModuleInfo])
    limitations: list[str] = field(default_factory=list[str])
    truncated: bool = False


# ---- the one package-root resolver -----------------------------------------------------------------------------


def _holder(app: object, modules: Mapping[str, object]) -> str | None:
    """Shortest name of a loaded module whose globals hold ``app``: ``vars()`` only, never getattr or a module hook."""
    names = [
        name
        for name, module in tuple(modules.items())
        if type(module) is ModuleType
        and name.partition(".")[0] != "sharpit"
        and any(value is app for value in tuple(vars(module).values()))
    ]
    real = [n for n in names if n != "__main__"]  # `python run.py` re-exporting myapp.main:app: __main__ is not the app
    return min(real or names, key=lambda n: (len(n), n), default=None)


def _main_package(modules: Mapping[str, object]) -> str | None:
    """``python -m pkg``: ``__main__.__package__`` names the package (read with ``vars()``); a script has none."""
    main = modules.get("__main__")
    package = vars(main).get("__package__") if type(main) is ModuleType else None
    return package if isinstance(package, str) and package else None


def _loaded_location(module: ModuleType) -> Path | None:
    namespace = vars(module)
    paths = namespace.get("__path__")
    if paths is not None:
        try:
            first = next((p for p in paths if isinstance(p, str)), None)
        except Exception:  # noqa: BLE001 - a custom __path__ object: degrade; never crash the host
            return None
        return Path(first) if first else None
    file = namespace.get("__file__")
    return Path(file) if isinstance(file, str) and file.endswith(".py") else None


def _search(top: str, search_path: Sequence[object]) -> Path | None:
    """Python's lookup order for a top-level name on disk (stat calls only): a package or module beats a namespace."""
    namespace: Path | None = None
    for entry in search_path:
        if not isinstance(entry, str):
            continue
        base = Path(entry or ".")
        if (base / top / "__init__.py").is_file():
            return base / top
        if (base / f"{top}.py").is_file():
            return base / f"{top}.py"
        if namespace is None and (base / top).is_dir():
            namespace = base / top
    return namespace


def resolve_package_root(
    app: object,
    modules: Mapping[str, object],
    *,
    app_package: str | None = None,
    search_path: Sequence[object] = (),  # sys.path may hold a non-str entry: skipped
    reasons: list[str] | None = None,
) -> Path | None:
    """The app's top-level package directory, or its file for a single-module app; None with a reason appended.

    An explicit ``app_package`` wins; else the module holding ``app`` in its globals (``type(app).__module__`` would
    name the framework; ``__main__`` only when nothing else holds it, then its ``__package__`` for ``python -m``).
    Both resolve through ``modules`` only, then through ``search_path`` on disk when the caller passes one (config's
    explicit ``config_scan`` names); never ``find_spec``, which imports parents.
    """
    notes = reasons if reasons is not None else []
    name = app_package or (_holder(app, modules) if app is not None else None)
    if not name:
        notes.append("no loaded module holds the application and app_package is not set")
        return None
    if name.partition(".")[0] == "__main__" and (name := _main_package(modules)) is None:
        notes.append("the application is defined in __main__ (a script run directly): not scanned; set app_package")
        return None
    top = name.partition(".")[0]
    module = modules.get(top)
    root = _loaded_location(module) if type(module) is ModuleType else _search(top, search_path)
    if root is None:
        notes.append(f"package {top!r} is not imported and has no source location (sharpit never imports it)")
    return root


def resolve_app_root(
    app: object,
    modules: Mapping[str, object],
    *,
    app_package: str | None = None,
    search_path: Sequence[object] = (),
    reasons: list[str] | None = None,
) -> Path | None:
    """The app package directory (parent of ``__init__.py`` when seen as a file), or file for single-module apps."""
    root = resolve_package_root(app, modules, app_package=app_package, search_path=search_path, reasons=reasons)
    if root is not None and root.name == "__init__.py":
        return root.parent
    return root


# ---- the bounded index -----------------------------------------------------------------------------------------


def _inside(real: str, real_root: str) -> bool:
    """``real`` (already a realpath) is under ``real_root`` (a normcased realpath)."""
    real = os.path.normcase(real)
    try:
        return os.path.commonpath([real, real_root]) == real_root
    except ValueError:  # another drive
        return False


def _module_name(root: Path, path: Path) -> str:
    parts = path.relative_to(root.parent).with_suffix("").parts
    return ".".join(parts[:-1] if len(parts) > 1 and parts[-1] == "__init__" else parts)


def _from_target(node: ast.ImportFrom, parts: list[str]) -> str | None:
    """The absolute module of a ``from`` import, None if it climbs out of ``parts``."""
    keep = len(parts) - node.level + 1
    if node.level and keep <= 0:
        return None
    base = parts[:keep] if node.level else []
    return ".".join([*base, node.module] if node.module else base)


def _imports(tree: ast.Module, package: str) -> tuple[str, ...]:
    """Absolute names of every import; a relative one is resolved against ``package``, dropped if it climbs out."""
    parts = package.split(".") if package else []
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and (target := _from_target(node, parts)):
            found.append(target)
    return tuple(dict.fromkeys(found))


def _parse(path: str, max_file_bytes: int) -> ast.Module | str:
    """The parsed module, or why it was skipped."""
    try:
        info = os.stat(path)
        if not stat.S_ISREG(info.st_mode):
            return "not a regular file"
        if info.st_size > max_file_bytes:
            return f"larger than {max_file_bytes} bytes"
        with open(path, "rb") as handle:
            data = handle.read(max_file_bytes + 1)
        if len(data) > max_file_bytes:  # a pseudo-file stats as 0 bytes; a file can grow after the stat
            return f"larger than {max_file_bytes} bytes"
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
        # undecodable bytes are replaced, as 0.3.0's getenv scan did: one bad comment must not hide a file
        return ast.parse(data.decode(encoding, errors="replace"), filename=path)
    except _READ_ERRORS as exc:
        return type(exc).__name__


def _add(index: SourceIndex, root: Path, path: Path, real: str, max_file_bytes: int) -> None:
    """Parse ``path`` (``real`` is its realpath, already checked inside the root) into the index."""
    tree = _parse(real, max_file_bytes)
    if isinstance(tree, str):
        index.limitations.append(f"{path}: {tree}")
        return
    name = _module_name(root, path)
    package = name if path.name == "__init__.py" else name.rpartition(".")[0]
    functions = tuple(n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef))
    index.modules.setdefault(name, ModuleInfo(name, path, tree, _imports(tree, package), functions))


def _entries(index: SourceIndex, directory: Path) -> list[os.DirEntry[str]]:
    try:
        with os.scandir(directory) as found:
            return sorted(found, key=lambda e: e.name)
    except OSError as exc:
        index.limitations.append(f"{directory}: {type(exc).__name__}")
        return []


def _stop(index: SourceIndex, reason: str) -> None:
    index.truncated = True
    index.limitations.append(reason)


def _python_files(
    index: SourceIndex, directory: Path, real_root: str, deadline: float, subdirs: list[Path]
) -> Iterator[tuple[Path, str] | None]:
    """Each ``.py`` file of ``directory`` with its realpath, its subdirectories into ``subdirs``; None: out of time."""
    for entry in _entries(index, directory):
        if time.monotonic() >= deadline:  # per entry: a deep tree without .py files must stop too
            yield None
            return
        real = os.path.realpath(entry.path)
        if entry.is_symlink() or entry.is_junction() or not _inside(real, real_root):
            continue  # never followed; containment also catches a link the entry flags miss
        if entry.is_dir(follow_symlinks=False):
            if entry.name not in _SKIP_DIRS:
                subdirs.append(Path(entry.path))
        elif entry.name.endswith(".py"):
            yield Path(entry.path), real


def _fill(index: SourceIndex, root: Path, max_files: int, max_file_bytes: int, deadline: float) -> None:
    real_root = os.path.normcase(os.path.realpath(root))
    if not os.path.isdir(real_root):  # a single-module app: that file only
        _add(index, root, root, os.path.realpath(root), max_file_bytes)
        return
    attempted = 0  # every .py file opened or refused counts, parsed or not
    stack = [root]
    while stack:
        subdirs: list[Path] = []
        for found in _python_files(index, stack.pop(), real_root, deadline, subdirs):
            if found is None:
                return _stop(index, f"stopped by the wall budget after {attempted} files")
            if attempted >= max_files:
                return _stop(index, f"stopped at {max_files} files (bounds: {max_files} files)")
            attempted += 1
            _add(index, root, *found, max_file_bytes)
        stack += reversed(subdirs)  # pre-order, sorted: files of a directory before its subdirectories
    return None


def _guarded_fill(index: SourceIndex, root: Path, max_files: int, max_file_bytes: int, deadline: float) -> None:
    try:
        _fill(index, root, max_files, max_file_bytes, deadline)
    except Exception as exc:  # noqa: BLE001 - defensive: a scan failure is a limitation; never a crash
        index.limitations.append(f"source scan failed: {type(exc).__name__}")


def build_index(
    root: Path,
    *,
    max_files: int = MAX_FILES,
    max_file_bytes: int = MAX_FILE_BYTES,
    wall_budget_s: float = 10.0,
    thread: bool = True,
) -> SourceIndex:
    """Index ``root`` (a package directory or one ``.py`` file) in a worker thread under a wall budget.

    ``thread=False`` runs on the caller's thread (config: its spec §14 exemption is attributed to the calling frame).
    The returned index is the caller's to drop; nothing here keeps it.
    """
    index = SourceIndex()
    deadline = time.monotonic() + wall_budget_s
    if not thread:
        _guarded_fill(index, root, max_files, max_file_bytes, deadline)
        return index
    args = (index, root, max_files, max_file_bytes, deadline)
    worker = threading.Thread(target=_guarded_fill, args=args, name="sharpit-appsource", daemon=True)
    worker.start()
    worker.join(wall_budget_s + 1.0)
    if worker.is_alive():  # one file outlived the budget: its partial index is not trusted
        return SourceIndex(limitations=[f"source scan exceeded its {wall_budget_s}s wall budget"], truncated=True)
    return index


# ---- config's getenv scan (moved from collectors/config/getenv_scan.py) ----------------------------------------


@dataclass
class GetenvFinding:
    key: str
    default: str | None
    location: str


def _is_os_attr(node: ast.expr, attr: str) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == attr
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def _literal_key(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _literal_default(call: ast.Call) -> str | None:
    # Non-literal defaults stay None: never evaluated.
    arg = call.args[1] if len(call.args) > 1 else next((k.value for k in call.keywords if k.arg == "default"), None)
    if isinstance(arg, ast.Constant) and arg.value is not None:
        return str(arg.value)
    return None


def _os_aliases(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Local names bound by ``from os import environ`` / ``from os import getenv``."""
    environ_names: set[str] = set()
    getenv_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "os" and node.level == 0:
            for alias in node.names:
                if alias.name == "environ":
                    environ_names.add(alias.asname or "environ")
                elif alias.name == "getenv":
                    getenv_names.add(alias.asname or "getenv")
    return environ_names, getenv_names


def _is_getenv(func: ast.expr, getenv_names: set[str], is_environ: Callable[[ast.expr], bool]) -> bool:
    return (
        _is_os_attr(func, "getenv")
        or (isinstance(func, ast.Name) and func.id in getenv_names)
        or (isinstance(func, ast.Attribute) and func.attr == "get" and is_environ(func.value))
    )


def getenv_findings(tree: ast.Module, location: str) -> list[GetenvFinding]:
    """Literal-key ``os.getenv``/``os.environ`` reads in one parsed module; ``location`` prefixes each line."""
    environ_names, getenv_names = _os_aliases(tree)

    def is_environ(n: ast.expr) -> bool:
        return _is_os_attr(n, "environ") or (isinstance(n, ast.Name) and n.id in environ_names)

    found: list[GetenvFinding] = []
    for node in ast.walk(tree):
        key: str | None = None
        default: str | None = None
        line = 0
        if isinstance(node, ast.Call) and node.args:
            if _is_getenv(node.func, getenv_names, is_environ):
                key, default, line = _literal_key(node.args[0]), _literal_default(node), node.lineno
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load) and is_environ(node.value):
            key, line = _literal_key(node.slice), node.lineno
        if key is not None:
            found.append(GetenvFinding(key, default, f"{location}:{line}"))
    return found


def scan_packages(roots: Sequence[Path]) -> list[GetenvFinding]:
    """Getenv reads under each root; location is ``<path relative to the root's parent>:<line>``. The index is
    dropped when this returns (spec §4.2: only the report is cached)."""
    findings: list[GetenvFinding] = []
    for root in roots:
        if not root.exists():
            continue
        index = build_index(root, thread=False)
        for module in index.modules.values():
            findings += getenv_findings(module.tree, module.path.relative_to(root.parent).as_posix())
    return findings
