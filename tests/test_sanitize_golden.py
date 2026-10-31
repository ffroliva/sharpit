import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sanitize_golden.py"
spec = importlib.util.spec_from_file_location("sanitize_golden", SCRIPT)
assert spec
assert spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_rejects_paths_outside_fixture_directories(tmp_path: Path):
    with pytest.raises(ValueError, match="under replica/evidence"):
        module.main(tmp_path, tmp_path / "out")
