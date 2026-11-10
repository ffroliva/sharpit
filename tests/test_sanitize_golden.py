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


def test_sanitiser_merges_meta_for_the_target_version(tmp_path: Path):
    source_meta = Path(__file__).parent / "fixtures" / "bootui" / "2.3.0" / "meta.json"
    error, dst = _tree(
        tmp_path / "rerun",
        {"overview/captured.json": {"name": "x"}},
        name="2.3.0",
        version="2.3.0",
    )
    assert error is None
    # Reuse the real lane B metadata in an isolated destination.
    (dst / "meta.json").write_text(source_meta.read_text(encoding="utf-8"), encoding="utf-8")
    src = tmp_path / "rerun" / "replica" / "evidence" / "2.3.0"
    (src / "uncaptured.json").write_text('{"overview": "not served"}', encoding="utf-8")
    module.main(src, dst, repo=tmp_path / "rerun", version="2.3.0")
    meta = json.loads((dst / "meta.json").read_text(encoding="utf-8"))
    assert meta["bootuiVersion"] == "2.3.0"
    for key, value in json.loads(source_meta.read_text(encoding="utf-8")).items():
        assert meta[key] == value
    for key in ("app", "profile", "captured", "uncaptured"):
        assert key in meta
    assert "2.2.0" not in json.dumps(meta)


def test_sanitiser_refuses_vendor_tokens_anywhere():
    tokens = (
        "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "gho_abcdefghijklmnopqrstuvwxyz0123456789",
        "ghu_abcdefghijklmnopqrstuvwxyz0123456789",
        "ghs_abcdefghijklmnopqrstuvwxyz0123456789",
        "ghr_abcdefghijklmnopqrstuvwxyz0123456789",
        "github_pat_abcdefghijklmnopqrstuvwxyz0123456789",
        "sk-12345678901234567890123456789012",
        "sk-ant-12345678901234567890123456789012",
        "Bearer abcdefghijklmnopqrstuvwxyz0123456789",
    )
    for token in tokens:
        assert module.find_secrets({"description": token}) == ["$.description"]
        assert module.find_secrets({"summary": f"captured {token} in prose"}) == ["$.summary"]
    assert module.find_secrets({"description": "task-list and disk-usage; Bearer is a scheme"}) == []


@pytest.mark.parametrize(
    "token",
    (
        "sk-proj-Ab1_cD2-" + "x" * 24,
        "sk-svcacct-" + "x" * 24,
        "token%3Dghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "TOKEN_ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "KEY_sk-ant-abcdefghijklmnopqrstuvwxyz0123456789",
        "bearer abcdefghijklmnopqrstuvwxyz0123456789",
        "BEARER abcdefghijklmnopqrstuvwxyz0123456789",
        "Bearer%20abcdefghijklmnopqrstuvwxyz0123456789",
        "Bearer+abcdefghijklmnopqrstuvwxyz0123456789",
    ),
)
def test_find_secrets_refuses_encoded_and_prefixed_tokens(token: str):
    assert module.find_secrets({"description": token}) == ["$.description"]


def test_find_secrets_handles_long_strings_quickly():
    import time

    started = time.perf_counter()
    assert module.find_secrets({"description": "x" * 200_000}) == []
    assert time.perf_counter() - started < 1


def test_enums_come_from_the_raw_capture(tmp_path: Path):
    error, dst = _tree(
        tmp_path,
        {"agent/captured.json": {"items": [{"state": "ACTIVE"}, {"state": "PAUSED"}]}},
        name="2.3.0",
    )
    assert error is None
    enums_path = dst / "agent" / "enums.raw.json"
    assert enums_path.is_file()
    enums = json.loads(enums_path.read_text(encoding="utf-8"))
    assert enums["$.items[].state"] == ["ACTIVE", "PAUSED"]


def test_enums_only_publish_enum_constants_from_raw_capture(tmp_path: Path):
    error, dst = _tree(
        tmp_path,
        {
            "agent/captured.json": {
                "message": "user alice@corp.example logged in from host WS-ALICE-01",
                "status": "UP",
            }
        },
        name="2.3.0",
    )
    assert error is None
    enums = json.loads((dst / "agent" / "enums.raw.json").read_text(encoding="utf-8"))
    assert enums == {"$.status": ["UP"]}


def test_enums_cap_distinct_values_per_key_path(tmp_path: Path):
    error, dst = _tree(
        tmp_path,
        {"agent/captured.json": {"status": [f"STATE_{i}" for i in range(65)]}},
        name="2.3.0",
    )
    assert error is None
    enums = json.loads((dst / "agent" / "enums.raw.json").read_text(encoding="utf-8"))
    assert len(enums["$.status[]"]) == 64


def test_version_comes_from_source_and_rejects_unknown_versions(tmp_path: Path):
    src = tmp_path / "replica" / "evidence" / "2.2.0"
    dst = tmp_path / "tests" / "fixtures" / "bootui" / "scratch"
    src.mkdir(parents=True)
    dst.mkdir(parents=True)
    (src / "agent").mkdir()
    (src / "agent" / "captured.json").write_text('{"status":"UP"}', encoding="utf-8")
    module.main(src, dst, repo=tmp_path)
    meta = json.loads((dst / "meta.json").read_text(encoding="utf-8"))
    assert meta["bootuiVersion"] == "2.2.0"
    assert json.loads((dst / "agent" / "captured.json").read_text(encoding="utf-8")) == {"status": "UP"}
    assert not (dst / "agent" / "enums.raw.json").exists()
    with pytest.raises(ValueError, match="version must be '2.2.0' or '2.3.0'"):
        module.main(src, dst, repo=tmp_path, version="scratch")


def test_shaping_keeps_every_key_path():
    raw = {
        "items": [
            "one",
            "two",
            "three",
            {"outer": {"first": "a"}},
            {"outer": {"second": "b"}},
        ]
    }
    shaped = module._shape_key_paths(raw)

    def key_paths(node: object, path: str = "$") -> set[str]:
        if isinstance(node, dict):
            return {f"{path}.{key}" for key, value in node.items()} | {
                item for key, value in node.items() for item in key_paths(value, f"{path}.{key}")
            }
        if isinstance(node, list):
            return set().union(*(key_paths(value, f"{path}[]") for value in node))
        return set()

    assert key_paths(shaped) == key_paths(raw)


def test_2_2_meta_content_remains_unchanged(tmp_path: Path):
    error, dst = _tree(tmp_path, {}, name="2.2.0")
    assert error is None
    meta = json.loads((dst / "meta.json").read_text(encoding="utf-8"))
    assert meta == module.META_2_2_0 | {"uncaptured": {}, "provisional": []}
