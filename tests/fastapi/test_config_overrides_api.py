"""``POST``/``DELETE {api}/config/overrides`` and the config report's override flags (W8 Task O2)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.config import overrides as overrides_mod

LOCAL = ("127.0.0.1", 50000)
URL = "/sharpit/api/config/overrides"
NAME = "O2_SAMPLE_KEY"


@pytest.fixture(autouse=True)
def isolated_environ(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    saved = dict(os.environ)
    monkeypatch.setattr(overrides_mod, "_ORIGINAL_ENVIRON", {})
    yield
    os.environ.clear()
    os.environ.update(saved)


def _client(file: Path, **options: Any) -> TestClient:
    app = FastAPI()
    merged: dict[str, Any] = {
        "enabled": "ON",
        "show_banner": False,
        "overrides_file": str(file),
        "expose_values": "FULL",
        **options,
    }
    install(app, **merged)
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False)


def _post(client: TestClient, body: Any) -> Any:
    return client.post(URL, json=body)


def _unchanged(file: Path, before_env: dict[str, str], before_file: bytes | None) -> None:
    assert dict(os.environ) == before_env
    assert (file.read_bytes() if file.exists() else None) == before_file


def _snapshot(file: Path) -> tuple[dict[str, str], bytes | None]:
    return dict(os.environ), (file.read_bytes() if file.exists() else None)


def test_post_creates_new_override_and_returns_dto(tmp_path: Path) -> None:
    # ported: ConfigControllerHttpCrudTests.postCreatesNewOverrideAndReturnsCorrectDto
    resp = _post(_client(tmp_path / "o.env"), {"name": NAME, "value": "v1"})
    assert resp.status_code == 200
    body = resp.json()
    assert (body["name"], body["value"], body["persisted"]) == (NAME, "v1", True)
    assert set(body) == {"name", "value", "previousValue", "persisted", "message"}
    assert os.environ[NAME] == "v1"


def test_post_is_idempotent_and_returns_previous_value(tmp_path: Path) -> None:
    # ported: ConfigControllerHttpCrudTests.postIsIdempotentAndReturnsPreviousValue
    client = _client(tmp_path / "o.env")
    assert _post(client, {"name": NAME, "value": "9090"}).status_code == 200
    body = _post(client, {"name": NAME, "value": "9191"}).json()
    assert (body["value"], body["previousValue"], body["persisted"]) == ("9191", "9090", True)


def test_delete_existing_override_returns_null_value_and_previous_display(tmp_path: Path) -> None:
    # ported: ConfigControllerHttpCrudTests.deleteExistingOverrideReturnsNullValueAndPreviousDisplay
    client = _client(tmp_path / "o.env")
    _post(client, {"name": NAME, "value": "to-delete"})
    resp = client.delete(f"{URL}/{NAME}")
    assert resp.status_code == 200
    body = resp.json()
    assert (body["name"], body["value"], body["previousValue"], body["persisted"]) == (NAME, None, "to-delete", True)
    assert NAME not in os.environ


def test_delete_non_existing_override_is_idempotent_and_returns_200(tmp_path: Path) -> None:
    # ported: ConfigControllerHttpCrudTests.deleteNonExistingOverrideIsIdempotentAndReturns200
    resp = _client(tmp_path / "o.env").delete(f"{URL}/does.not.exist")
    assert resp.status_code == 200
    body = resp.json()
    assert (body["name"], body["value"], body["persisted"]) == ("does.not.exist", None, True)


def test_persisted_state_survives_across_installs(tmp_path: Path) -> None:
    # ported: ConfigControllerHttpCrudTests.persistedStateSurvivesAcrossControllerInstances
    file = tmp_path / "o.env"
    _post(_client(file), {"name": NAME, "value": "7777"})
    props = _client(file).get("/sharpit/api/config", params={"q": NAME}).json()["properties"]
    row = next(p for p in props if p["name"] == NAME)
    assert (row["value"], row["override"]) == ("7777", True)


def test_restart_warning_message_is_present_for_overridden_property(tmp_path: Path) -> None:
    # ported: ConfigControllerHttpCrudTests.restartWarningMessageIsPresentForOverriddenProperty
    body = _post(_client(tmp_path / "o.env"), {"name": NAME, "value": "9090"}).json()
    assert "restart" in body["message"]


def test_config_report_override_flags_real(tmp_path: Path) -> None:
    client = _client(tmp_path / "o.env")
    before = client.get("/sharpit/api/config").json()
    assert before["overrideCount"] == 0
    _post(client, {"name": NAME, "value": "x"})
    after = client.get("/sharpit/api/config").json()
    assert after["overrideCount"] == 1
    only = client.get("/sharpit/api/config", params={"overridesOnly": "true"}).json()
    assert [p["name"] for p in only["properties"]] == [NAME]
    assert only["properties"][0]["override"] is True


def test_config_get_never_writes(tmp_path: Path) -> None:
    file = tmp_path / "o.env"
    client = _client(file)
    _post(client, {"name": NAME, "value": "x"})
    env, content = _snapshot(file)
    assert client.get("/sharpit/api/config").status_code == 200
    _unchanged(file, env, content)


def test_post_masks_secret_value_in_response(tmp_path: Path) -> None:
    body = _post(
        _client(tmp_path / "o.env", expose_values="MASKED"), {"name": "O2_DB_PASSWORD", "value": "hunter2-secret"}
    ).json()
    assert "hunter2-secret" not in str(body)
    assert body["value"] != "hunter2-secret"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"value": "x"}, "'name' must be provided"),
        ({"name": None, "value": "x"}, "'name' must be provided"),
        ({"name": "   ", "value": "x"}, "Property name must not be blank"),
        ({"name": 5, "value": "x"}, "'name' must be a string"),
        ({"name": ["a"], "value": "x"}, "'name' must be a string"),
        ({"name": NAME, "value": 5}, "'value' must be a string"),
        ({"name": NAME, "value": True}, "'value' must be a string"),
        ({"name": NAME, "value": "x", "persist": "yes"}, "'persist' must be a boolean"),
        ({"name": NAME, "value": "x", "persist": 1}, "'persist' must be a boolean"),
        ({"name": "bad name!", "value": "x"}, "Property name is invalid"),
        ({"name": "SHARPIT_ENABLED", "value": "x"}, "sharpit settings cannot be overridden at runtime."),
        ({"name": "Sharpit_Token", "value": "x"}, "sharpit settings cannot be overridden at runtime."),
        ({"name": "path", "value": "x"}, "Environment variable 'path' cannot be overridden at runtime."),
        ({"name": NAME, "value": "a\nb"}, "Property value must not contain control characters or newlines"),
        ({"name": NAME, "value": "a\x00b"}, "Property value must not contain control characters or newlines"),
    ],
)
def test_post_refusals_are_400_and_change_nothing(tmp_path: Path, body: dict[str, Any], message: str) -> None:
    file = tmp_path / "o.env"
    client = _client(file)
    env, content = _snapshot(file)
    resp = _post(client, body)
    assert (resp.status_code, resp.json()) == (400, {"error": message})
    _unchanged(file, env, content)


@pytest.mark.parametrize("raw", ["not json", "[1]", '"s"', "null", ""])
def test_post_non_object_body_is_400(tmp_path: Path, raw: str) -> None:
    file = tmp_path / "o.env"
    client = _client(file)
    env, content = _snapshot(file)
    resp = client.post(URL, content=raw, headers={"content-type": "application/json"})
    assert resp.status_code == 400
    assert set(resp.json()) == {"error"}
    _unchanged(file, env, content)


def test_post_wrong_content_type_is_415(tmp_path: Path) -> None:
    client = _client(tmp_path / "o.env")
    resp = client.post(URL, content='{"name": "A", "value": "b"}', headers={"content-type": "text/plain"})
    assert resp.status_code == 415
    assert "A" not in os.environ


def test_post_oversized_body_is_413(tmp_path: Path) -> None:
    file = tmp_path / "o.env"
    client = _client(file)
    env, content = _snapshot(file)
    resp = _post(client, {"name": NAME, "value": "x" * (200 * 1024)})
    assert resp.status_code == 413
    _unchanged(file, env, content)


def test_invalid_name_is_never_echoed(tmp_path: Path) -> None:
    resp = _post(_client(tmp_path / "o.env"), {"name": "tok=ghp_abcdefghijklmnopqrstuvwxyz0123456789", "value": "x"})
    assert resp.status_code == 400
    assert "ghp_" not in resp.text


def test_delete_refused_name_is_400_and_changes_nothing(tmp_path: Path) -> None:
    file = tmp_path / "o.env"
    client = _client(file)
    env, content = _snapshot(file)
    resp = client.delete(f"{URL}/SHARPIT_ENABLED")
    assert (resp.status_code, resp.json()) == (400, {"error": "sharpit settings cannot be overridden at runtime."})
    _unchanged(file, env, content)


def test_write_failure_is_500_with_the_file_message_and_rolls_back(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    file = blocker / "o.env"  # the parent is a file: the save fails
    client = _client(file)
    env, _ = _snapshot(file)
    resp = _post(client, {"name": NAME, "value": "x"})
    assert (resp.status_code, resp.json()) == (500, {"error": f"Unable to write sharpit overrides file: {file}"})
    assert dict(os.environ) == env
    assert client.get("/sharpit/api/config").json()["overrideCount"] == 0


def test_unexpected_failure_never_leaks_the_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(tmp_path / "o.env")

    def boom(*_a: Any, **_k: Any) -> None:
        raise KeyError("secret-detail")

    monkeypatch.setattr(overrides_mod.ConfigOverrideService, "put", boom)
    resp = _post(client, {"name": NAME, "value": "x"})
    assert resp.status_code == 500
    assert "secret-detail" not in resp.text


# --- gates: each refusal proves the override file and os.environ are unchanged -------------------------------------


def _gate_client(tmp_path: Path, **options: Any) -> tuple[TestClient, Path]:
    file = tmp_path / "o.env"
    return _client(file, **options), file


@pytest.mark.parametrize(
    "options",
    [{"read_only": True}, {"panels": {"config": {"read_only": True}}}],
    ids=["global", "panel"],
)
@pytest.mark.parametrize("method", ["POST", "DELETE"])
def test_read_only_refuses_and_changes_nothing(tmp_path: Path, options: dict[str, Any], method: str) -> None:
    client, file = _gate_client(tmp_path, **options)
    env, content = _snapshot(file)
    path = f"{URL}/{NAME}" if method == "DELETE" else URL
    resp = client.request(method, path, json=None if method == "DELETE" else {"name": NAME, "value": "x"})
    assert resp.status_code == 403
    assert resp.json()["panel"] == "config"
    assert "read-only" in resp.json()["reason"]
    _unchanged(file, env, content)


def test_disabled_panel_refuses_and_changes_nothing(tmp_path: Path) -> None:
    client, file = _gate_client(tmp_path, panels={"config": {"enabled": False}})
    env, content = _snapshot(file)
    assert _post(client, {"name": NAME, "value": "x"}).status_code == 403
    assert client.delete(f"{URL}/{NAME}").status_code == 403
    _unchanged(file, env, content)


def test_inactive_sharpit_answers_404_and_changes_nothing(tmp_path: Path) -> None:
    client, file = _gate_client(tmp_path, enabled="OFF")
    env, content = _snapshot(file)
    assert _post(client, {"name": NAME, "value": "x"}).status_code == 404
    assert client.delete(f"{URL}/{NAME}").status_code == 404
    _unchanged(file, env, content)


def test_guard_cross_site_refuses_and_changes_nothing(tmp_path: Path) -> None:
    client, file = _gate_client(tmp_path)
    env, content = _snapshot(file)
    resp = client.post(URL, json={"name": NAME, "value": "x"}, headers={"Origin": "http://evil.example"})
    assert resp.status_code == 403
    _unchanged(file, env, content)


def test_guard_foreign_host_refuses_and_changes_nothing(tmp_path: Path) -> None:
    client, file = _gate_client(tmp_path)
    env, content = _snapshot(file)
    assert client.post(URL, json={"name": NAME, "value": "x"}, headers={"Host": "evil.example"}).status_code == 403
    _unchanged(file, env, content)


def test_guard_remote_without_token_refuses_and_changes_nothing(tmp_path: Path) -> None:
    app = FastAPI()
    file = tmp_path / "o.env"
    install(app, enabled="ON", show_banner=False, overrides_file=str(file))
    remote = TestClient(app, base_url="http://localhost", client=("203.0.113.9", 50000))
    env, content = _snapshot(file)
    assert remote.post(URL, json={"name": NAME, "value": "x"}).status_code == 403
    _unchanged(file, env, content)


def test_override_routes_rest_only() -> None:
    from sharpit.engine import tools

    listed = [str(t.name) for t in tools.TOOLS] + [str(c) for c in tools.COMMANDS]
    assert [n for n in listed if "override" in n.lower()] == []
