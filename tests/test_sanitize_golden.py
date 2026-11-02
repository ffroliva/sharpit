import importlib.util
import json
from pathlib import Path
from typing import Any

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


def _tree(tmp_path: Path, files: dict[str, object], name: str = "2.2.0", **kwargs: Any) -> tuple[object, Path]:
    """Run ``main`` on a throw-away repo layout under ``tmp_path``; return (error or None, destination)."""
    src = tmp_path / "replica" / "evidence" / name
    dst = tmp_path / "tests" / "fixtures" / "bootui" / name
    src.mkdir(parents=True)
    dst.mkdir(parents=True)
    for rel, body in files.items():
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_text(json.dumps(body), encoding="utf-8")
    error: object = None
    try:
        module.main(src, dst, repo=tmp_path, **kwargs)
    except (ValueError, SystemExit) as exc:
        error = exc
    return error, dst


def test_sanitise_keeps_urls_and_scrubs_embedded_paths():
    urls = ["jdbc:postgresql://db:5432/x", "http://x/y", "https://a.b/c?d=e:/f", "classpath:/db/changelog.xml"]
    assert [module.sanitise(u) for u in urls] == urls
    assert module.sanitise(r"file [C:\Program Files\a b\c.class]") == "file [/path]"
    assert module.sanitise(r"opened 'C:\Users\bob\my dir\x.txt' ok") == "opened '/path' ok"
    assert module.sanitise("at C:/dev/app/x.py line 3") == "at /path line 3"
    assert module.sanitise("log at /home/bob/app/x.log done") == "log at /path done"
    assert module.sanitise("see /Users/bob/x") == "see /path"


def test_sanitise_scrubs_more_2_2_0_epoch_fields_and_keeps_nulls():
    raw = {
        "capturedAt": 5,
        "timestamp": 6,
        "firstSeen": 7,
        "lastSeen": 8,
        "generatedAt": 9,
        "startTimestamp": 1,
        "endTimestamp": 2,
        "epochMillis": 3,
        "oldestRetainedAt": 4,
        "durationMicros": 123,
        "clientAddress": "10.89.0.1",
    }
    out = module.sanitise(raw, nested=True)
    assert {k: out[k] for k in raw if k not in ("durationMicros", "clientAddress")} == dict.fromkeys(
        [k for k in raw if k not in ("durationMicros", "clientAddress")], 1700000000000
    )
    assert out["durationMicros"] == 1000
    assert out["clientAddress"] == "127.0.0.1"
    nulls = module.sanitise({"scannedAt": None, "startupTimeMillis": None, "startedAt": None}, nested=True)
    assert nulls == {"scannedAt": None, "startupTimeMillis": None, "startedAt": None}


def test_shape_golden_keeps_one_item_per_distinct_shape_and_real_nulls():
    assert module.shape_golden([{"v": "a"}, {"v": True}, {"v": "b"}]) == [{"v": "a"}, {"v": True}]
    assert module.shape_golden([{"x": None}, {"x": {"y": 1}}, {"x": None}]) == [{"x": None}, {"x": {"y": 1}}]
    assert module.shape_golden({"items": [1, 2, 3, 4, 5]}) == {"items": [1, 2, 3]}


def test_main_refuses_a_secret_that_only_shows_before_shaping(tmp_path: Path):
    rows = [{"name": "a", "value": None}, {"name": "db.password", "value": "hunter2"}]
    error, dst = _tree(tmp_path, {"config/captured.json": {"properties": rows}})
    assert isinstance(error, SystemExit)
    assert not (dst / "config" / "captured.json").exists()


def test_main_refuses_error_envelope_bodies(tmp_path: Path):
    spring = {"timestamp": 1, "status": 500, "error": "Internal Server Error", "path": "/x"}
    for body in ({"error": "forbidden"}, {"error": "x", "other": 1}, spring):
        error, dst = _tree(tmp_path / str(len(str(body))), {"overview/captured.json": body})
        assert isinstance(error, SystemExit)
        assert not (dst / "overview" / "captured.json").exists()


def test_main_writes_captured_tree_and_keeps_nullable_and_provisional(tmp_path: Path):
    dst = tmp_path / "tests" / "fixtures" / "bootui" / "2.2.0"
    (dst / "overview").mkdir(parents=True)
    (dst / "overview" / "nullable.json").write_text('{"keep": "me"}', encoding="utf-8")
    (dst / "meta.json").write_text('{"provisional": ["alembic"]}', encoding="utf-8")
    src = tmp_path / "replica" / "evidence" / "2.2.0"
    (src / "overview").mkdir(parents=True)
    (src / "overview" / "captured.json").write_text('{"runId": "abc", "name": "x"}', encoding="utf-8")
    (src / "http-exchanges").mkdir()
    (src / "http-exchanges" / "routes.captured.json").write_text('{"checkedAt": 9}', encoding="utf-8")
    error: object = None
    try:
        module.main(src, dst, repo=tmp_path)
    except ValueError as exc:
        error = exc
    assert error is None
    assert (dst / "overview" / "captured.json").is_file()
    assert json.loads((dst / "overview" / "captured.json").read_text(encoding="utf-8"))["runId"] == "00000000"
    assert (dst / "http-exchanges" / "routes.captured.json").is_file()
    assert (dst / "overview" / "nullable.json").read_text(encoding="utf-8") == '{"keep": "me"}'
    assert json.loads((dst / "meta.json").read_text(encoding="utf-8"))["provisional"] == ["alembic"]


def test_main_layout_follows_the_source_folder_name(tmp_path: Path):
    error, dst = _tree(tmp_path, {"overview.json": {"a": 1}, "S-shots/stray.captured.json": {"b": 2}}, name="1.17.0")
    assert error is None
    assert (dst / "overview.json").is_file()
    assert not (dst / "S-shots").exists()
    assert "bootui" in json.loads((dst / "meta.json").read_text(encoding="utf-8"))
    forced, forced_dst = _tree(tmp_path / "forced", {"overview/captured.json": {"a": 1}}, name="x", layout="nested")
    assert forced is None
    assert (forced_dst / "overview" / "captured.json").is_file()
