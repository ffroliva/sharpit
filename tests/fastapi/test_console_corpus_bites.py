import json
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient
from tests.console_corpus import assert_corpus_match, build_app, isolated_environment, normalise, record

TRANSPORT_CORPUS = Path(__file__).parents[1] / "fixtures" / "console_corpus" / "transport.json"
GET_CORPUS = Path(__file__).parents[1] / "fixtures" / "console_corpus" / "panels_get.json"


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

    expected = _transport("index_active")
    assert actual["headers"]["x-frame-options"] == "SAMEORIGIN"
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
