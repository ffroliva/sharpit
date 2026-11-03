"""The Architecture advisor's source reads over a real fixture package (spec §4.2, §4.5, §5.5; review fix 1).

Each fixture is a top-level package written under ``tmp_path``, put on ``sys.path`` and loaded in ``sys.modules`` (as
the host's own import would), and named to sharpit by its dotted name, so the scan really runs. Every test asserts the
scan ran (``SCANNED``/``PARTIAL`` and source files opened) before it asserts what was or was not read.
"""

from __future__ import annotations

import builtins
import contextlib
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine import appsource

LOCAL = ("127.0.0.1", 50000)


def _write(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, files: dict[str, str]) -> Path:
    """A package on sys.path, loaded in sys.modules (no import runs: the module object carries its location)."""
    pkg = tmp_path / name
    for rel, text in {"__init__.py": "", **files}.items():
        _write(pkg / rel, text)
    monkeypatch.syspath_prepend(str(tmp_path))
    module = types.ModuleType(name)
    module.__file__ = str(pkg / "__init__.py")
    module.__path__ = [str(pkg)]
    monkeypatch.setitem(sys.modules, name, module)
    return pkg


def _client(app_package: str, **options: Any) -> TestClient:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False, app_package=app_package, **options)
    return TestClient(app, base_url="http://localhost", client=LOCAL)


@contextlib.contextmanager
def _opened_sources(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Path]]:
    """Every ``.py`` path opened through ``builtins.open`` while the block runs (appsource reads with ``open``)."""
    opened: list[Path] = []
    real_open = builtins.open

    def spy(file: Any, *args: Any, **kwargs: Any) -> Any:
        if str(file).endswith(".py"):
            opened.append(Path(file).resolve())
        return real_open(file, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(builtins, "open", spy)
        yield opened


def _link_dir(target: Path, link: Path) -> bool:
    """A directory link (a junction on Windows, a symlink elsewhere); False when the platform refuses it."""
    try:
        if sys.platform == "win32":
            import _winapi  # noqa: PLC0415

            _winapi.CreateJunction(str(target), str(link))
        else:
            link.symlink_to(target, target_is_directory=True)
    except OSError:
        return False
    return True


def test_real_scan_bounded_files_and_symlinks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg = _package(tmp_path, monkeypatch, "arch_sym_app", {"mod.py": "A = 1\n"})
    outside = tmp_path / "arch_outside_dir"
    _write(outside / "secret.py", "SECRET = 42\n")
    if not _link_dir(outside, pkg / "linked"):
        pytest.skip("directory links unavailable")
    client = _client("arch_sym_app")

    with _opened_sources(monkeypatch) as opened:
        data = client.post("/sharpit/api/architecture/scan").json()

    assert data["scan"]["status"] == "SCANNED"
    assert pkg.resolve() / "mod.py" in opened
    assert [p for p in opened if p.is_relative_to(outside.resolve())] == []


def test_max_files_setting_bounds_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _package(tmp_path, monkeypatch, "arch_many_app", {f"m{i}.py": f"X{i} = {i}\n" for i in range(6)})
    client = _client("arch_many_app", architecture_max_files=3)

    data = client.post("/sharpit/api/architecture/scan").json()

    assert data["scan"]["status"] == "PARTIAL"
    assert any("stopped at 3 files" in lim for lim in data["evidence"]["limitations"])


def test_max_file_bytes_setting_bounds_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _package(tmp_path, monkeypatch, "arch_big_app", {"big.py": "X = 1\n" + "# pad\n" * 400})
    client = _client("arch_big_app", architecture_max_file_bytes=1024)

    data = client.post("/sharpit/api/architecture/scan").json()

    assert any("larger than 1024 bytes" in lim for lim in data["evidence"]["limitations"])


def test_real_scan_then_get_opens_no_source_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg = _package(
        tmp_path, monkeypatch, "arch_open_app", {"a.py": "import arch_open_app.b\n", "b.py": "import arch_open_app.a\n"}
    )
    client = _client("arch_open_app")
    with _opened_sources(monkeypatch) as scanned:
        report = client.post("/sharpit/api/architecture/scan").json()
    assert report["scan"]["status"] == "SCANNED"
    assert pkg.resolve() / "a.py" in scanned
    scan_id = report["violationDetails"]["scanId"]

    with _opened_sources(monkeypatch) as opened:
        cached = client.get("/sharpit/api/architecture")
        page = client.get("/sharpit/api/architecture/rules/ARCH-PKG-001/violations", params={"scanId": scan_id})

    assert cached.status_code == 200
    assert page.status_code == 200
    assert page.json()["page"]["total"] >= 1
    assert opened == []


def test_real_scan_reads_only_app_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = _package(tmp_path, monkeypatch, "arch_target_pkg", {"mod.py": "C = 3\n"})
    _write(tmp_path / "arch_other_pkg" / "__init__.py")
    _write(tmp_path / "arch_other_pkg" / "mod.py", "D = 4\n")
    _write(tmp_path / "arch_loose.py", "E = 5\n")
    client = _client("arch_target_pkg")

    with _opened_sources(monkeypatch) as opened:
        data = client.post("/sharpit/api/architecture/scan").json()

    assert data["scan"]["status"] == "SCANNED"
    assert target.resolve() / "mod.py" in opened
    assert [p for p in opened if not p.is_relative_to(target.resolve())] == []


def test_app_package_not_imported_is_not_scanned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path / "arch_disk_only" / "__init__.py")
    _write(tmp_path / "arch_disk_only" / "mod.py", "F = 6\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    client = _client("arch_disk_only")

    with _opened_sources(monkeypatch) as opened:
        data = client.post("/sharpit/api/architecture/scan").json()

    assert data["scan"]["status"] == "NOT_SCANNED"
    assert "not imported" in data["scan"]["message"]
    assert opened == []


def test_loaded_namespace_package_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ns = tmp_path / "arch_ns_app"
    _write(ns / "main.py", "x = 1\n")
    module = types.ModuleType("arch_ns_app")
    module.__path__ = [str(ns)]  # a namespace package: no __init__.py, no __file__
    monkeypatch.setitem(sys.modules, "arch_ns_app", module)
    client = _client("arch_ns_app")

    data = client.post("/sharpit/api/architecture/scan").json()

    assert data["scan"]["status"] == "SCANNED"
    assert data["classesAnalyzed"] >= 1


def test_architecture_uses_the_one_resolver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg = tmp_path / "arch_spy_pkg"
    _write(pkg / "__init__.py")
    _write(pkg / "mod.py", "G = 7\n")
    calls: list[str | None] = []

    def spy(app: object, modules: object, **kwargs: Any) -> Path | None:
        calls.append(kwargs.get("app_package"))
        return pkg

    monkeypatch.setattr(appsource, "resolve_package_root", spy)
    data = _client("arch_spy_pkg").post("/sharpit/api/architecture/scan").json()

    assert "arch_spy_pkg" in calls
    assert data["scan"]["status"] == "SCANNED"
    assert data["classesAnalyzed"] >= 1
