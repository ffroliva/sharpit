"""The importlinter contracts come from the package's own sys.path entry and nowhere else (spec §5.5; review fix 4)."""

from __future__ import annotations

import builtins
from pathlib import Path
from typing import Any

import pytest

from sharpit.engine.collectors.architecture.contracts import read_contracts

CONTRACT = '[[tool.importlinter.contracts]]\nname = "{name}"\ntype = "layers"\nlayers = ["a", "b"]\n'


def _write(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _spy_open(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    opened: list[Path] = []
    real_open = builtins.open

    def spy(file: Any, *args: Any, **kwargs: Any) -> Any:
        opened.append(Path(file).resolve())
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy)
    return opened


def test_pyproject_ignores_ancestor_sys_path_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    top = tmp_path / "top"
    _write(top / "pyproject.toml", CONTRACT.format(name="ancestor"))
    src = top / "sub" / "proj" / "src"
    pkg = src / "arch_pp_app"
    _write(pkg / "__init__.py")
    opened = _spy_open(monkeypatch)

    contracts, _ = read_contracts(pkg, [str(top), str(src)])

    assert [c.name for c in contracts] == []
    assert (top / "pyproject.toml").resolve() not in opened


def test_pyproject_read_from_src_layout_entry_not_ancestor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    top = tmp_path / "top"
    _write(top / "pyproject.toml", CONTRACT.format(name="ancestor"))
    proj = top / "sub" / "proj"
    _write(proj / "pyproject.toml", CONTRACT.format(name="own"))
    pkg = proj / "src" / "arch_pp_app"
    _write(pkg / "__init__.py")
    opened = _spy_open(monkeypatch)

    contracts, _ = read_contracts(pkg, [str(top), str(proj / "src")])

    assert [c.name for c in contracts] == ["own"]
    assert (proj / "pyproject.toml").resolve() in opened
    assert (top / "pyproject.toml").resolve() not in opened


def test_pyproject_not_read_when_package_entry_not_on_sys_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path / "pyproject.toml", CONTRACT.format(name="parent"))
    pkg = tmp_path / "arch_pp_app"
    _write(pkg / "__init__.py")
    opened = _spy_open(monkeypatch)

    contracts, _ = read_contracts(pkg, [])

    assert [c.name for c in contracts] == []
    assert opened == []
