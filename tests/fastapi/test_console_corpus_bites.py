import copy
import json
import os
import re
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from tests.console_corpus import assert_corpus_match, build_app, isolated_environment, normalise, record

TRANSPORT_CORPUS = Path(__file__).parents[1] / "fixtures" / "console_corpus" / "transport.json"
GET_CORPUS = Path(__file__).parents[1] / "fixtures" / "console_corpus" / "panels_get.json"
_OS_LEAK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("windows_drive_path", re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]")),
    ("backslash_segment", re.compile(r"\\[^\\\s]+")),
    ("linux_home", re.compile(r"/home/")),
    ("macos_users", re.compile(r"/Users/")),
    ("site_packages", re.compile(r"site-packages")),
    ("virtualenv", re.compile(r"\.venv")),
    (
        "platform_value",
        re.compile(r"(?:\b(?:py)?win32\b|\b(?:darwin|linux|SYSTEMROOT|WINDIR)\b|<TEMP_PATH>)", re.IGNORECASE),
    ),
)


def _transport(case_id: str) -> dict[str, Any]:
    return json.loads(TRANSPORT_CORPUS.read_text(encoding="utf-8"))[case_id]


def test_corpus_comparison_detects_a_changed_response_header(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import sharpit.fastapi.adapter as adapter

    original = adapter.security_headers

    def changed_headers(kind: str) -> list[tuple[str, str]]:
        return [(name, "SAMEORIGIN" if name == "X-Frame-Options" else value) for name, value in original(kind)]

    monkeypatch.setattr(adapter, "security_headers", changed_headers)
    with isolated_environment(str(tmp_path)):
        app = build_app(state_dir=str(tmp_path))
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            actual = record(client, "GET", "/sharpit/")

    expected = _transport("security_headers")
    assert actual["headers"]["x-frame-options"] == "SAMEORIGIN"
    assert {
        "content-security-policy",
        "permissions-policy",
        "pragma",
        "cache-control",
        "referrer-policy",
        "x-content-type-options",
        "x-frame-options",
    } <= set(expected["headers"])
    with pytest.raises(AssertionError):
        assert_corpus_match(actual, expected)


def test_corpus_comparison_detects_a_changed_guard_status(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import sharpit.fastapi.adapter as adapter

    original = adapter.guard.decide_guard

    def changed_guard(facts: Any, settings: Any, token: str | None, gateway: str | None) -> Any:
        denial = original(facts, settings, token, gateway)
        if denial is None:
            return None
        return adapter.guard.Denial(418, denial.body, denial.headers)

    monkeypatch.setattr(adapter.guard, "decide_guard", changed_guard)
    with isolated_environment(str(tmp_path)):
        app = build_app(state_dir=str(tmp_path))
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            actual = record(client, "GET", "/sharpit/api/panels", headers={"Host": "evil.example"})

    expected = _transport("disallowed_host")
    assert actual["status"] == 418
    with pytest.raises(AssertionError):
        assert_corpus_match(actual, expected)


def test_corpus_comparison_detects_a_changed_panel_body_field(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import sharpit.fastapi.routes as routes

    original = routes.panels_report

    def changed_panels(*args: Any, **kwargs: Any) -> dict[str, Any]:
        report = original(*args, **kwargs)
        report["platform"] = "flask"
        return report

    monkeypatch.setattr(routes, "panels_report", changed_panels)
    with isolated_environment(str(tmp_path)):
        app = build_app(state_dir=str(tmp_path))
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            actual = normalise(record(client, "GET", "/sharpit/api/panels"))

    expected = json.loads(GET_CORPUS.read_text(encoding="utf-8"))["/api/panels"]
    assert actual["body"]["platform"] == "flask"
    with pytest.raises(AssertionError):
        assert_corpus_match(actual, expected)


def test_normaliser_keeps_structure_and_stable_values() -> None:
    payload = {
        "latencySampleCount": 7,
        "maxDurationSeconds": 9,
        "pinnedDurationMicros": 11,
        "heapDumpEnabled": True,
        "exemplarRequestIds": ["request-12345678", "request-87654321"],
        "threads": {"items": [{"id": "thread-12345678", "name": "worker"}]},
        "tasks": {"items": ["task-a", "task-b"]},
        "stateCounts": {"running": 3},
        "deadlockedThreadIds": ["thread-12345678"],
        "page": 4,
        "startupTimeMillis": None,
    }
    expected = normalise(payload)
    mutations = []
    removed = dict(payload)
    removed.pop("latencySampleCount")
    mutations.append(removed)
    shrunk = dict(payload)
    shrunk["exemplarRequestIds"] = payload["exemplarRequestIds"][:1]
    mutations.append(shrunk)
    flipped = dict(payload)
    flipped["heapDumpEnabled"] = False
    mutations.append(flipped)
    changed = dict(payload)
    changed["latencySampleCount"] = 8
    mutations.append(changed)
    for mutated in mutations:
        assert normalise(mutated) != expected


def test_corpus_contains_masked_config_secret_and_rejects_identity_masker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from sharpit.engine.masking import Masker

    with isolated_environment(str(tmp_path)):
        app = build_app(state_dir=str(tmp_path))
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            actual = record(client, "GET", "/sharpit/api/config")
    expected = json.loads(GET_CORPUS.read_text(encoding="utf-8"))["/api/config"]
    assert "s3cr3t-value" not in json.dumps(expected)
    assert "******" in json.dumps(expected)
    assert_corpus_match(normalise(actual), expected)

    monkeypatch.setattr(Masker, "mask", lambda self, name, value: (value, False))
    with isolated_environment(str(tmp_path)):
        app = build_app(state_dir=str(tmp_path))
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            unmasked = normalise(record(client, "GET", "/sharpit/api/config"))
    assert "s3cr3t-value" in json.dumps(unmasked)
    with pytest.raises(AssertionError):
        assert_corpus_match(unmasked, expected)


def _os_specific_leaks(value: Any, location: str = "") -> list[str]:
    if isinstance(value, dict):
        leaks: list[str] = []
        for key, item in value.items():
            leaks.extend(_os_specific_leaks(item, f"{location}.{key}" if location else str(key)))
        return leaks
    if isinstance(value, list):
        leaks = []
        for index, item in enumerate(value):
            leaks.extend(_os_specific_leaks(item, f"{location}[{index}]"))
        return leaks
    if not isinstance(value, str):
        return []
    leaks = [f"{location}: {label} in {value!r}" for label, pattern in _OS_LEAK_PATTERNS if pattern.search(value)]
    executables = {sys.executable, sys.executable.replace("\\", "/")} - {""}
    if any(executable in value for executable in executables):
        leaks.append(f"{location}: sys_executable in {value!r}")
    return leaks


def _assert_no_os_specific_values(corpus: Any) -> None:
    leaks = _os_specific_leaks(corpus)
    assert leaks == []


def test_recorded_corpus_has_no_os_specific_values() -> None:
    transport = json.loads(TRANSPORT_CORPUS.read_text(encoding="utf-8"))
    panels_get = json.loads(GET_CORPUS.read_text(encoding="utf-8"))
    _assert_no_os_specific_values(transport)
    _assert_no_os_specific_values(panels_get)

    for sample in (
        r"C:\Users\alice\app",
        "C:/Users/alice/app",
        r"relative\segment",
        "/home/alice/app",
        "/Users/alice/app",
        "/usr/lib/site-packages/pkg",
        "/work/.venv/lib",
        sys.executable,
        "win32",
        "darwin",
        "linux",
    ):
        planted = copy.deepcopy(panels_get)
        planted["/api/overview"]["body"]["contextPath"] = sample
        with pytest.raises(AssertionError):
            _assert_no_os_specific_values(planted)


def test_isolated_environment_and_normaliser_are_os_independent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_sqla = types.ModuleType("sqlalchemy")
    fake_sqla.__version__ = "2.0.0"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sqlalchemy", fake_sqla)

    with isolated_environment(str(tmp_path)):
        assert dict(os.environ) == {
            "HOME": "/sharpit-home",
            "USERPROFILE": "/sharpit-home",
            "TMP": "/sharpit-tmp",
            "TEMP": "/sharpit-tmp",
            "PATH": "/sharpit/bin",
            "SHARPIT_TEST_API_TOKEN": "s3cr3t-value",
        }
        app = build_app(state_dir=str(tmp_path))
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            activity = normalise(record(client, "GET", "/sharpit/api/activity"))

    expected_activity = json.loads(GET_CORPUS.read_text(encoding="utf-8"))["/api/activity"]
    assert_corpus_match(activity, expected_activity)
    posix_bean = {"resource": "/home/runner/.venv/lib/python3.14/site-packages/fastapi/routing.py:267"}
    assert normalise(posix_bean) == {"resource": "<SOURCE_REF>"}
