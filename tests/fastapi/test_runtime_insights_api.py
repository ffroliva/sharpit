"""``GET {api}/runtime-insights``, ``/insights/{id}``, ``/resource-profile`` (GET, POST, stop) and the two read tools
(BootUI ``RuntimeInsightsController``, ``McpToolCatalog`` rows ``get_runtime_insights`` and ``get_runtime_insight``)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.insights import profile
from sharpit.engine.collectors.insights.finding import Evaluation, Finding
from sharpit.engine.collectors.insights.service import InsightsService
from sharpit.engine.guard import PANEL_ACCESS_DENIED

LOCAL = ("127.0.0.1", 50000)
API = "/sharpit/api/runtime-insights"
PROFILE = f"{API}/resource-profile"
AI = {"source": "ai", "operation": "chat", "inputTokens": 5, "outputTokens": 7}
REPORT_KEYS = [
    "available", "unavailableReason", "window", "coverage", "checks", "observations", "limitations", "notExercised",
    "notExercisedOmitted",
]  # fmt: skip


@dataclass(frozen=True)
class FakeKind:
    kind: str = "errors-behind-2xx"
    title: str = "Errors behind 2xx"
    minimum_tier: str = "REQUEST_ID"
    reads: frozenset[str] = frozenset({"ai"})
    optional_reads: frozenset[str] = frozenset()
    evaluate: object = field(default=lambda _snapshot: Evaluation(1, [_finding()]))


def _finding() -> Finding:
    return Finding(
        "GET /x", "GET /x", True, "repeated a SELECT 3 times", 4, 3, ["Check the call site."], ["r-1"],
        ["call site"], [["a.py:1"]], [],
    )  # fmt: skip


def _client(*, seeded: bool = False, **options: Any) -> tuple[TestClient, Any]:
    app = FastAPI()
    handle = install(app, **{"enabled": "ON", "show_banner": False, "config_scan": False, **options})
    ctx = handle.context
    if seeded and ctx.capture.journal is not None:
        ctx.capture.journal.offer(AI)
        ctx.lazy("runtime-insights", lambda: InsightsService(ctx.capture.journal, [FakeKind()]))
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False), ctx


def _mcp(client: TestClient, tool: str, **arguments: Any) -> dict[str, Any]:
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
    return client.post("/sharpit/api/mcp", json=call).json().get("result", {})


def test_get_returns_the_report_with_every_bootui_key() -> None:
    client, _ = _client()
    response = client.get(API)
    assert response.status_code == 200
    body = response.json()
    assert list(body) == REPORT_KEYS
    assert body["available"] is True
    assert len(body["checks"]) == 28


def test_the_panel_is_listed_now_that_it_is_implemented() -> None:
    client, _ = _client()
    panels = {panel["id"] for panel in client.get("/sharpit/api/panels").json()["panels"]}
    assert "runtime-insights" in panels


def test_get_with_the_journal_disabled_is_unavailable_with_the_setting_to_set() -> None:
    client, _ = _client(runtime_journal_enabled=False)
    response = client.get(API)
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert "SHARPIT_RUNTIME_JOURNAL_ENABLED" in body["unavailableReason"]


def test_insight_by_id_returns_the_observation_and_its_evidence() -> None:
    client, _ = _client(seeded=True)
    listed = client.get(API)
    assert listed.status_code == 200
    observation = listed.json()["observations"][0]
    detail = client.get(f"{API}/insights/{observation['id']}").json()
    assert detail["available"] is True
    assert detail["observation"] == observation
    assert detail["rows"] == [{"cells": ["a.py:1"]}]


def test_insight_unknown_id_answers_bootui_not_found() -> None:
    client, _ = _client(seeded=True)
    response = client.get(f"{API}/insights/conformance-unknown:0000000000")
    assert response.status_code == 200
    assert response.json()["unavailableReason"] == (
        "No observation conformance-unknown:0000000000 in this run's retained events: "
        "it may have been evicted or cleared."
    )


def test_resource_profile_get_is_the_unavailable_floor() -> None:
    client, _ = _client()
    response = client.get(PROFILE)
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "UNAVAILABLE"
    assert body["maxDurationSeconds"] == 30
    assert body["reason"] == profile.NO_SAMPLER


def test_resource_profile_without_the_resources_source_names_the_setting() -> None:
    client, _ = _client(runtime_journal_sources="http,sql")
    assert client.get(PROFILE).json()["reason"] == profile.RESOURCES_OFF


def _started_since(before: set[int | None]) -> list[str]:
    """Threads started since ``before``, except AnyIO's worker pool, which grows on demand to run sync routes."""
    return [t.name for t in threading.enumerate() if t.ident not in before and t.name != "AnyIO worker thread"]


@pytest.mark.parametrize("suffix", ["", "/stop"])
def test_resource_profile_post_answers_the_floor_and_starts_nothing(suffix: str) -> None:
    client, _ = _client(runtime_journal_sources="http,sql,resources", resources_jfr_max_duration="45s")
    client.get(PROFILE)  # warm-up: the first sync route starts the AnyIO worker thread, which is not a sampler
    before = {t.ident for t in threading.enumerate()}
    response = client.post(PROFILE + suffix)
    assert response.status_code == 200
    assert response.json()["state"] == "UNAVAILABLE"
    assert response.json()["reason"] == profile.NO_SAMPLER
    assert response.json()["maxDurationSeconds"] == 45
    # a thread that ends meanwhile is fine; a thread the POST started is not (a count equality flaked both ways on CI)
    assert _started_since(before) == []


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    for name in ("start", "stop"):
        original = getattr(profile.ResourceProfile, name)
        monkeypatch.setattr(
            profile.ResourceProfile, name, lambda self, n=name, o=original: (calls.append(n), o(self))[1]
        )
    return calls


@pytest.mark.parametrize("suffix", ["", "/stop"])
@pytest.mark.parametrize("options", [{"read_only": True}, {"panels": {"runtime-insights": {"read_only": True}}}])
def test_resource_profile_post_refused_read_only_handler_not_run(
    spy: list[str], suffix: str, options: dict[str, Any]
) -> None:
    client, _ = _client(**options)
    assert client.get(PROFILE).status_code == 200
    response = client.post(PROFILE + suffix)
    assert response.status_code == 403
    assert response.json()["error"] == PANEL_ACCESS_DENIED
    assert "read-only" in response.json()["reason"]
    assert spy == []


@pytest.mark.parametrize("suffix", ["", "/stop"])
def test_resource_profile_post_refused_when_the_panel_is_disabled(spy: list[str], suffix: str) -> None:
    client, _ = _client(panels={"runtime-insights": {"enabled": False}})
    assert client.get(API).status_code == 403
    assert client.post(PROFILE + suffix).status_code == 403
    assert spy == []


@pytest.mark.parametrize("suffix", ["", "/stop"])
def test_resource_profile_post_is_404_when_sharpit_is_inactive(spy: list[str], suffix: str) -> None:
    client, _ = _client(enabled="OFF")
    assert client.post(PROFILE + suffix).status_code == 404
    assert spy == []


@pytest.mark.parametrize("suffix", ["", "/stop"])
def test_resource_profile_post_is_refused_from_another_site(spy: list[str], suffix: str) -> None:
    client, _ = _client()
    assert client.get(PROFILE).status_code == 200  # the route is served: the refusal below is the guard's
    response = client.post(PROFILE + suffix, headers={"Origin": "http://evil.example", "Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403
    assert spy == []


def test_no_read_starts_anything(no_side_effects: SideEffectGuard) -> None:
    # ported: RuntimeInsightsReadPurityArchitectureTests.onlyTheProfileResourcesActionStartsAJfrSession
    no_side_effects.unblock_network()
    client, _ = _client(seeded=True, mcp_enabled="ON")
    with client:
        no_side_effects.block_network()
        client.get("/sharpit/api/panels")  # the portal's worker thread starts with the first sync route
        before = {t.ident for t in threading.enumerate()}
        listed = client.get(API)
        assert listed.status_code == 200
        observation = listed.json()["observations"][0]
        assert client.get(f"{API}/insights/{observation['id']}").status_code == 200
        assert client.get(PROFILE).status_code == 200
        assert _mcp(client, "get_runtime_insights").get("isError") is False
        assert _mcp(client, "get_runtime_insight", id=observation["id"]).get("isError") is False
        assert _started_since(before) == []
    assert no_side_effects.violations == []


def test_insights_tool_answers_the_agent_list_with_the_bootui_default_limit() -> None:
    client, _ = _client(seeded=True, mcp_enabled="ON")
    listed = _mcp(client, "get_runtime_insights").get("structuredContent", {})
    assert listed.get("available") is True
    assert [o["kind"] for o in listed["observations"]] == ["errors-behind-2xx"]
    assert listed["observations"][0]["exemplarRequestId"] == "r-1"
    assert listed["observations"][0]["verify"] == "Check the call site."
    steps = {step["tool"]: step for step in listed["next"]}
    assert steps["get_runtime_insight"]["arguments"] == {"id": listed["observations"][0]["id"]}
    assert steps["get_request_profile"]["arguments"] == {"id": "r-1"}


def test_insight_tool_answers_the_agent_detail() -> None:
    client, _ = _client(seeded=True, mcp_enabled="ON")
    listed = client.get(API)
    assert listed.status_code == 200
    observation = listed.json()["observations"][0]
    shown = _mcp(client, "get_runtime_insight", id=observation["id"]).get("structuredContent", {})
    assert shown.get("available") is True
    assert shown["observation"]["id"] == observation["id"]
    assert shown["whatToCheck"] == ["Check the call site."]
    assert shown["rows"] == [{"cells": ["a.py:1"]}]


def test_insight_tool_unknown_id_is_a_tool_error_naming_the_list_call() -> None:
    client, _ = _client(seeded=True, mcp_enabled="ON")
    result = _mcp(client, "get_runtime_insight", id="x:0000000000")
    assert result.get("isError") is True
    assert "List the current observation ids with get_runtime_insights." in result.get("content", [{}])[0].get(
        "text", ""
    )


def test_cli_insights_list_and_show_are_registered() -> None:
    client, _ = _client(cli_enabled=True)
    commands = {tool["name"]: tool["command"] for tool in client.get("/sharpit/api/cli").json()["tools"]}
    assert commands.get("get_runtime_insights") == "insights list"
    assert commands.get("get_runtime_insight") == "insights show"
