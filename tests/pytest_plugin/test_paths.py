from __future__ import annotations

import ntpath
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace

import pytest

from sharpit.engine.testsession.swallowed import site_identity, swallowing_sites
from sharpit.pytest_plugin import paths, swallowed


@pytest.mark.parametrize("subdirectory", ["src", "..cache"])
def test_relative_location_keeps_directories_under_root(tmp_path: Path, subdirectory: str) -> None:
    assert paths.relative_location(str(tmp_path / subdirectory / "x.py"), tmp_path) == f"{subdirectory}/x.py"


def test_relative_location_keeps_outside_paths_absolute(tmp_path: Path) -> None:
    outside = tmp_path / "other" / "x.py"
    assert paths.relative_location(str(outside), tmp_path / "root") == outside.as_posix()


def test_swallowed_location_keeps_its_existing_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    filename = tmp_path / "..cache" / "x.py"
    source = "try:\n    raise TypeError()\nexcept Exception:\n    pass\n"
    (site,) = swallowing_sites(source)
    monkeypatch.setattr(swallowed, "swallowing_site", lambda *_: site)

    fact = swallowed._fact(compile(source, str(filename), "exec"), 0, TypeError, str(tmp_path), str(tmp_path))

    assert fact is not None
    assert fact.location == f"..cache/x.py:{site.line}"
    assert fact.identity == site_identity(filename.as_posix(), site, "TypeError")


@pytest.fixture
def windows_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "os", SimpleNamespace(path=ntpath))
    monkeypatch.setattr(paths, "Path", PureWindowsPath)


@pytest.mark.parametrize("drive, expected", [("D", "D:/root/src/x.py"), ("c", "src/x.py")])
def test_relative_location_uses_windows_drive_rules(windows_paths: None, drive: str, expected: str) -> None:
    assert paths.relative_location(f"{drive}:/root/src/x.py", "C:/root") == expected


@pytest.mark.parametrize(
    "site, expected",
    [
        (None, None),
        ("C:/root/src/x.py:8", "src/x.py:8"),
        ("C:/other/x.py:8", "C:/other/x.py:8"),
        ("D:/root/src/x.py:8", "D:/root/src/x.py:8"),
        ("C:8", "C:8"),
        ("C:/root/src/x.py", "C:/root/src/x.py"),
        ("C:/root/src/x.py:unknown", "C:/root/src/x.py:unknown"),
        ("outside application code", "outside application code"),
        ("outside application code:8", "outside application code:8"),
        (
            "outside application code (Player.name declared at C:/root/src/x.py:8)",
            "outside application code (Player.name declared at src/x.py:8)",
        ),
        (
            "outside application code (Player.name declared at C:/root/src/x.py)",
            "outside application code (Player.name declared at C:/root/src/x.py)",
        ),
    ],
)
def test_relative_site_only_rewrites_a_numbered_location(windows_paths: None, site: str | None, expected: str | None):
    try:
        actual = paths._relative_site(site, PureWindowsPath("C:/root"))
    except ValueError:
        actual = "raised ValueError"
    assert actual == expected
