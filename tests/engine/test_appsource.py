"""engine/appsource.py: the bounded app-source index and the one package-root resolver (spec §4.2)."""

from __future__ import annotations

import ast
import builtins
import gc
import os
import stat
import sys
import types
import weakref
from pathlib import Path
from typing import Any

import pytest

from sharpit.engine import appsource
from sharpit.engine.activation import ActivationStatus
from sharpit.engine.collectors.config import config_report
from sharpit.engine.context import SharpitContext
from sharpit.settings import SharpitSettings

SRC = Path(__file__).resolve().parents[2] / "src" / "sharpit"
CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "getenv_corpus"
ACTIVATION = ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ())


def _write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _module(name: str, file: Path | None = None, package: Path | None = None, **values: object) -> types.ModuleType:
    module = types.ModuleType(name)
    if file is not None:
        module.__file__ = str(file)
    if package is not None:
        module.__path__ = [str(package)]
    vars(module).update(values)
    return module


def _ctx(scan: tuple[str, ...] | bool, caller: str | None = None) -> SharpitContext:
    settings = SharpitSettings(config_scan=scan)
    return SharpitContext(settings, ACTIVATION, None, caller_module=caller)  # pyright: ignore[reportArgumentType]


def test_appsource_never_imports_or_follows_symlinks(tmp_path: Path) -> None:
    pkg = tmp_path / "trap_pkg_appsource"
    _write(pkg / "__init__.py")
    _write(pkg / "mod.py", "import builtins\nbuiltins._appsource_imported = True\ndef handler():\n    pass\n")
    outside = tmp_path / "outside"
    _write(outside / "o.py", "def leaked():\n    pass\n")
    linked: list[str] = []
    if sys.platform == "win32":
        import _winapi  # noqa: PLC0415 - Windows only

        _winapi.CreateJunction(str(outside), str(pkg / "jlink"))
        linked.append("trap_pkg_appsource.jlink.o")
    try:
        (pkg / "slink.py").symlink_to(outside / "o.py")
        (pkg / "sdir").symlink_to(outside, target_is_directory=True)
        linked += ["trap_pkg_appsource.slink", "trap_pkg_appsource.sdir.o"]
    except OSError:  # symlinks need developer mode on Windows; the junction still covers containment
        pass

    index = appsource.build_index(pkg)

    assert "trap_pkg_appsource.mod" in index.modules
    assert index.modules["trap_pkg_appsource.mod"].functions == ("handler",)
    assert "trap_pkg_appsource.mod" not in sys.modules
    assert not hasattr(builtins, "_appsource_imported")
    assert linked
    for name in linked:
        assert name not in index.modules, name
    assert not any(m.path.is_relative_to(outside) for m in index.modules.values())


def test_bounded_files_and_size(tmp_path: Path) -> None:
    pkg = tmp_path / "bounded"
    for n in range(4):
        _write(pkg / f"m{n}.py", f"X{n} = {n}\n")
    _write(pkg / "zz_big.py", "#" * 2048 + "\n")

    capped = appsource.build_index(pkg, max_files=2)
    sized = appsource.build_index(pkg, max_file_bytes=1024)

    assert len(capped.modules) == 2
    assert capped.truncated is True
    assert sorted(sized.modules) == ["bounded.m0", "bounded.m1", "bounded.m2", "bounded.m3"]
    assert sized.truncated is False
    assert any("zz_big.py" in reason for reason in sized.limitations)


def test_fifo_and_device_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg = tmp_path / "special"
    _write(pkg / "ok.py", "A = 1\n")
    fifo = _write(pkg / "fifo.py", "B = 2\n")
    real_stat = os.stat

    def fake_stat(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        result = real_stat(path, *args, **kwargs)
        if os.path.basename(os.fsdecode(path)) == fifo.name:  # pyright: ignore[reportUnknownArgumentType]
            values = list(result)
            values[stat.ST_MODE] = stat.S_IFIFO | 0o644
            return os.stat_result(values)
        return result

    monkeypatch.setattr(appsource.os, "stat", fake_stat)
    index = appsource.build_index(pkg, thread=False)

    assert "special.ok" in index.modules
    assert "special.fifo" not in index.modules
    assert any("fifo.py" in reason for reason in index.limitations)


def test_recursion_error_is_a_limitation(tmp_path: Path) -> None:
    pkg = tmp_path / "deep"
    _write(pkg / "fine.py", "import os\nfrom .sibling import x\n")
    _write(pkg / "nested.py", "x = " + "(" * 200_000 + ")" * 200_000 + "\n")
    _write(pkg / "broken.py", "def (:\n")

    index = appsource.build_index(pkg)

    assert "deep.fine" in index.modules
    assert index.modules["deep.fine"].imports == ("os", "deep.sibling")
    assert "deep.nested" not in index.modules
    assert any("nested.py" in reason for reason in index.limitations)
    assert any("broken.py" in reason for reason in index.limitations)


def test_resolve_package_root_from_factory_app(tmp_path: Path) -> None:
    pkg = _write(tmp_path / "factory_app" / "__init__.py").parent
    app = types.SimpleNamespace()  # type(app).__module__ is "types": the resolver must find the holder module
    modules: dict[str, object] = {
        "factory_app": _module("factory_app", pkg / "__init__.py", pkg),
        "factory_app.main": _module("factory_app.main", pkg / "main.py", app=app),
        "types": types,
    }

    assert appsource.resolve_package_root(app, modules) == pkg


def test_single_module_app_indexes_only_that_file(tmp_path: Path) -> None:
    solo = _write(tmp_path / "solo_app.py", "import os\nAPP = object()\ndef create():\n    pass\n")
    _write(tmp_path / "neighbour.py", "def other():\n    pass\n")
    app = object()

    root = appsource.resolve_package_root(app, {"solo_app": _module("solo_app", solo, app=app)})
    assert root == solo
    index = appsource.build_index(solo)

    assert sorted(index.modules) == ["solo_app"]
    assert index.modules["solo_app"].functions == ("create",)


def test_main_module_app_not_scanned_with_reason(tmp_path: Path) -> None:
    app = object()
    reasons: list[str] = []

    root = appsource.resolve_package_root(
        app, {"__main__": _module("__main__", _write(tmp_path / "run.py"), app=app)}, reasons=reasons
    )

    assert root is None
    assert len(reasons) == 1
    assert "__main__" in reasons[0]


def test_app_package_setting_never_imports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    loaded = _write(tmp_path / "loaded_pkg_appsource" / "__init__.py").parent
    _write(tmp_path / "lazy_parent_appsource" / "__init__.py", "import builtins\nbuiltins._appsource_parent = True\n")
    _write(tmp_path / "lazy_parent_appsource" / "child.py")
    monkeypatch.syspath_prepend(str(tmp_path))
    modules: dict[str, object] = {
        "loaded_pkg_appsource": _module("loaded_pkg_appsource", loaded / "__init__.py", loaded)
    }
    reasons: list[str] = []

    found = appsource.resolve_package_root(None, modules, app_package="loaded_pkg_appsource")
    missing = appsource.resolve_package_root(
        None, sys.modules, app_package="lazy_parent_appsource.child", reasons=reasons
    )

    assert found == loaded
    assert missing is None
    assert "lazy_parent_appsource" not in sys.modules
    assert not hasattr(builtins, "_appsource_parent")
    assert any("lazy_parent_appsource" in reason for reason in reasons)


def _root_resolvers_outside_appsource() -> list[str]:
    found: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if path.name == "appsource.py" and path.parent.name == "engine":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            name = node.attr if isinstance(node, ast.Attribute) else node.id if isinstance(node, ast.Name) else None
            if name in ("find_spec", "submodule_search_locations"):
                found.append(f"{path.relative_to(SRC).as_posix()}:{node.lineno} {name}")
    return found


def test_config_uses_the_one_resolver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg = tmp_path / "cfg_app_appsource"
    _write(pkg / "__init__.py")
    _write(pkg / "conf.py", 'import os\nX = os.getenv("ONE_RESOLVER_KEY")\n')
    calls: list[str | None] = []

    def spy(app: object, modules: object, **kwargs: Any) -> Path | None:
        calls.append(kwargs.get("app_package"))
        return pkg

    monkeypatch.setattr(appsource, "resolve_package_root", spy)
    report = config_report(_ctx(True, caller="cfg_app_appsource.main"), None, None, False, None, None, environ={})

    assert calls == ["cfg_app_appsource.main"]
    assert "ONE_RESOLVER_KEY" in [s["name"] for s in report["propertySuggestions"]]
    assert _root_resolvers_outside_appsource() == []


def test_source_index_not_retained_after_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(CORPUS))
    real = appsource.build_index
    refs: list[weakref.ref[appsource.SourceIndex]] = []

    def recording(root: Path, **kwargs: Any) -> appsource.SourceIndex:
        index = real(root, **kwargs)
        refs.append(weakref.ref(index))
        return index

    monkeypatch.setattr(appsource, "build_index", recording)
    ctx = _ctx(("pkg",))
    report = config_report(ctx, None, None, False, None, None, environ={})
    gc.collect()

    assert "FORM_A" in [s["name"] for s in report["propertySuggestions"]]
    assert len(refs) == 1
    assert refs[0]() is None


# ---- fix round 1 (council-claude #1-#3, review-gemini #1) ---------------------------------------------------------


def test_main_reexport_resolves_the_real_package(tmp_path: Path) -> None:
    # `python run.py` with `from myapp.main import app`: __main__ re-exports the app, myapp.main defines it
    pkg = _write(tmp_path / "myapp" / "__init__.py").parent
    app = object()
    modules: dict[str, object] = {
        "myapp": _module("myapp", pkg / "__init__.py", pkg),
        "myapp.main": _module("myapp.main", pkg / "main.py", app=app),
        "__main__": _module("__main__", _write(tmp_path / "run.py"), app=app),
    }

    assert appsource.resolve_package_root(app, modules) == pkg


def test_python_dash_m_package_resolves(tmp_path: Path) -> None:
    # `python -m myapp`: only __main__ (myapp/__main__.py) holds the app; its __package__ names the package
    pkg = _write(tmp_path / "myapp" / "__init__.py").parent
    app = object()
    main = _module("__main__", _write(pkg / "__main__.py"), app=app, __package__="myapp")
    modules: dict[str, object] = {"myapp": _module("myapp", pkg / "__init__.py", pkg), "__main__": main}

    assert appsource.resolve_package_root(app, modules) == pkg


def test_app_package_beats_autodetect(tmp_path: Path) -> None:
    other = _write(tmp_path / "other_pkg" / "__init__.py").parent
    mine = _write(tmp_path / "mine_pkg" / "__init__.py").parent
    app = object()
    modules: dict[str, object] = {
        "other_pkg": _module("other_pkg", other / "__init__.py", other, app=app),
        "mine_pkg": _module("mine_pkg", mine / "__init__.py", mine),
    }

    assert appsource.resolve_package_root(app, modules, app_package="mine_pkg") == mine


def test_app_package_overrides_a_script_main(tmp_path: Path) -> None:
    # `python run.py` defining the app itself: not scanned by default, but app_package must fix it as the reason says
    pkg = _write(tmp_path / "myapp" / "__init__.py").parent
    app = object()
    modules: dict[str, object] = {
        "myapp": _module("myapp", pkg / "__init__.py", pkg),
        "__main__": _module("__main__", _write(tmp_path / "run.py"), app=app),
    }

    assert appsource.resolve_package_root(app, modules, app_package="myapp") == pkg


def test_wall_budget_checked_per_directory_entry(tmp_path: Path) -> None:
    deep = tmp_path / "deep_dirs"
    for n in range(40):  # wide, not deep (Windows MAX_PATH); no .py file anywhere
        (deep / f"d{n}" / "sub").mkdir(parents=True)

    index = appsource.build_index(deep, wall_budget_s=0.0, thread=False)

    assert index.truncated is True
    assert any("budget" in reason for reason in index.limitations)


def test_unparsable_files_count_toward_max_files(tmp_path: Path) -> None:
    pkg = tmp_path / "broken_many"
    for n in range(6):
        _write(pkg / f"b{n}.py", "def (:\n")

    index = appsource.build_index(pkg, max_files=2, thread=False)

    assert index.truncated is True
    assert len(index.limitations) == 3


def test_file_grown_past_the_size_bound_after_stat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg = tmp_path / "grown"
    _write(pkg / "small.py", "A = 1\n")
    grown = _write(pkg / "grown.py", "B = 2\n" + "#" * 2048 + "\n")
    real_stat = os.stat

    def zero_size(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
        result = real_stat(path, *args, **kwargs)
        if os.path.basename(os.fsdecode(path)) == grown.name:  # pyright: ignore[reportUnknownArgumentType]
            values = list(result)
            values[stat.ST_SIZE] = 0  # a pseudo-file, or one that grew between stat and read
            return os.stat_result(values)
        return result

    monkeypatch.setattr(appsource.os, "stat", zero_size)
    index = appsource.build_index(pkg, max_file_bytes=1024, thread=False)

    assert "grown.small" in index.modules
    assert "grown.grown" not in index.modules
    assert any("grown.py" in reason for reason in index.limitations)
