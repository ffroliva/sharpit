from pathlib import Path

from sharpit.settings import load_settings


def test_default_state_dir_is_per_test(tmp_path: Path) -> None:
    assert load_settings({}, {}).state_dir == str(tmp_path / "state")


def test_explicit_state_dir_still_overrides_the_test_default(tmp_path: Path) -> None:
    state_dir = tmp_path / "explicit"
    assert load_settings({"state_dir": str(state_dir)}, {}).state_dir == str(state_dir)


def test_explicit_state_dir_environment_still_overrides(tmp_path: Path) -> None:
    state_dir = tmp_path / "environment"
    assert load_settings({}, {"SHARPIT_STATE_DIR": str(state_dir)}).state_dir == str(state_dir)
