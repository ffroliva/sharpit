"""scripts/dev/compare_shots.py: stable screenshots must match byte for byte; live ones are only listed."""

from pathlib import Path

import pytest
from _load import load_script

compare_shots = load_script("scripts/dev/compare_shots.py")


def _folder(root: Path, name: str, files: dict[str, bytes]) -> Path:
    folder = root / name
    folder.mkdir()
    for file, data in files.items():
        (folder / file).write_bytes(data)
    return folder


def test_identical_runs_pass(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    files = {"a.png": b"1", "b.png": b"2"}
    folders = [_folder(tmp_path, n, files) for n in ("b1", "b2", "af")]
    assert compare_shots.main(*folders) == 0
    assert "0 regressions" in capsys.readouterr().out


def test_a_file_that_moves_between_the_before_runs_is_live_and_allowed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    b1 = _folder(tmp_path, "b1", {"a.png": b"1", "live.png": b"x"})
    b2 = _folder(tmp_path, "b2", {"a.png": b"1", "live.png": b"y"})
    af = _folder(tmp_path, "af", {"a.png": b"1", "live.png": b"z"})
    assert compare_shots.main(b1, b2, af) == 0
    assert "live (check by eye): live.png" in capsys.readouterr().out


def test_a_stable_file_that_changes_is_a_regression(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    b1 = _folder(tmp_path, "b1", {"a.png": b"1"})
    b2 = _folder(tmp_path, "b2", {"a.png": b"1"})
    af = _folder(tmp_path, "af", {"a.png": b"2"})
    assert compare_shots.main(b1, b2, af) == 1
    assert "CHANGED: a.png" in capsys.readouterr().out


def test_a_missing_file_is_a_regression(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    b1 = _folder(tmp_path, "b1", {"a.png": b"1"})
    b2 = _folder(tmp_path, "b2", {"a.png": b"1"})
    af = _folder(tmp_path, "af", {})
    assert compare_shots.main(b1, b2, af) == 1
    assert "MISSING: a.png" in capsys.readouterr().out
