import importlib.util
import json
import shutil
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


def test_sanitize_golden_scrubs_2_2_0_volatile_keys_and_secrets():
    raw = {
        "instanceId": "a1b2c3d4-real",
        "runId": "8d1a2c7c",
        "startedAt": 1793578694874,
        "checkedAt": 1793578695102,
        "oldestTimestamp": 1793578600000,
        "newestTimestamp": 1793578690000,
        "nested": [{"runId": "ffffffff", "checkedAt": 5, "keep": "kept"}],
    }
    out = module.sanitise(raw)
    assert out["instanceId"] == "00000000"
    assert out["runId"] == "00000000"
    assert out["startedAt"] == 1700000000000
    assert out["checkedAt"] == 1700000000000
    assert out["oldestTimestamp"] == 1700000000000
    assert out["newestTimestamp"] == 1700000000000
    assert out["nested"] == [{"runId": "00000000", "checkedAt": 1700000000000, "keep": "kept"}]
    assert module.find_secrets(out) == []


def test_sanitize_golden_writes_captured_tree_and_meta_without_touching_nullable(tmp_path: Path):
    repo = Path(__file__).resolve().parents[1]
    src = repo / "replica" / "evidence" / "2.2.0-test-tree"
    dst = repo / "tests" / "fixtures" / "bootui" / "2.2.0-test-tree"
    (src / "http-exchanges").mkdir(parents=True)
    try:
        (src / "overview").mkdir()
        (src / "overview" / "captured.json").write_text('{"runId": "abc", "name": "x"}', encoding="utf-8")
        (src / "http-exchanges" / "routes.captured.json").write_text('{"checkedAt": 9}', encoding="utf-8")
        (dst / "overview").mkdir(parents=True)
        (dst / "overview" / "nullable.json").write_text('{"keep": "me"}', encoding="utf-8")
        module.main(src, dst)
        assert (dst / "overview" / "captured.json").is_file()
        assert json.loads((dst / "overview" / "captured.json").read_text(encoding="utf-8"))["runId"] == "00000000"
        assert (dst / "http-exchanges" / "routes.captured.json").is_file()
        assert (dst / "overview" / "nullable.json").read_text(encoding="utf-8") == '{"keep": "me"}'
    finally:
        shutil.rmtree(src, ignore_errors=True)
        shutil.rmtree(dst, ignore_errors=True)
