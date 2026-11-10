"""Unit tests for machine values collector and leak gate integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.ci import artifact_scan
from scripts.dev.machine_values import (
    REPO_ROOT,
    collect_machine_values,
    write_machine_values,
)


def test_leak_gate_refuses_machine_values(tmp_path: Path) -> None:
    canary = "stub_canary_super_secret_login_42"
    values_file = tmp_path / "canary_values.txt"
    write_machine_values(values_file, values=[canary])

    clean_dir = tmp_path / "clean"
    clean_dir.mkdir()
    (clean_dir / "panel.json").write_text(json.dumps({"status": "UP", "path": "/path"}), encoding="utf-8")

    # Clean tree passes
    ret_clean = artifact_scan.main(["--values-file", str(values_file), "--require", str(clean_dir)])
    assert ret_clean == 0, "clean tree must pass the scan"

    # Planted tree fails
    planted_dir = tmp_path / "planted"
    planted_dir.mkdir()
    (planted_dir / "dirty.json").write_text(
        json.dumps({"error": f"failed for user {canary} at /home"}),
        encoding="utf-8",
    )
    ret_planted = artifact_scan.main(["--values-file", str(values_file), "--require", str(planted_dir)])
    assert ret_planted == 1, "planted fixture holding machine value must fail the scan"


def test_machine_values_never_written_inside_the_repo(tmp_path: Path) -> None:
    # Must refuse write inside the repository root
    with pytest.raises(ValueError, match="inside the git repo"):
        write_machine_values(REPO_ROOT / "temp_leak_values.txt")

    out_file = tmp_path / "machine_values.txt"
    write_machine_values(out_file)
    assert out_file.is_file(), "output file must be written"
    lines = [line.strip() for line in out_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) > 0, "output file must contain machine values"


def test_machine_values_collection() -> None:
    custom_env = {
        "USERPROFILE": "C:\\Users\\test_dev_user_xyz",
        "PATH": "C:\\Windows\\system32;C:\\custom_secret_tool_dir;C:\\bin",
        "SECRET_ENV_VAR": "my_super_secret_token_value",
        "SHORT": "abc",
        "SYSTEMROOT": "C:\\Windows",
    }
    values = collect_machine_values(custom_env)
    assert len(values) > 0, "collected values must not be empty"
    assert "my_super_secret_token_value" in values
    assert "C:\\custom_secret_tool_dir" in values
    assert "abc" not in values, "short values (<6) must be excluded"
    assert "C:\\Windows" not in values, "common system value must be excluded"
