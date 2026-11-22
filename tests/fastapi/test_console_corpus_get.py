import json
import os
from pathlib import Path

from starlette.testclient import TestClient
from tests.console_corpus import assert_corpus_match, build_app, get_routes, isolated_environment, normalise, record

CORPUS = Path(__file__).parents[1] / "fixtures" / "console_corpus" / "panels_get.json"

DEFERRED = (
    ("/api/activity/request/{id}", "requires a concrete recorded request id"),
    ("/api/ai/chats/{spanId}", "requires a concrete recorded span id"),
    ("/api/architecture/rules/{rule_id}/violations", "requires a concrete recorded rule id"),
    ("/api/claude-code/sessions/{id}", "requires a concrete path parameter value"),
    ("/api/claude-code/sessions/{id}/events", "requires a concrete path parameter value"),
    (
        "/api/claude-code/sessions/{id}/events/{eventId}/raw",
        "file response coverage is deferred to a dedicated fixture",
    ),
    ("/api/activity/stream", "server-sent events are covered by F1b"),
    ("/api/claude-code/stream", "server-sent events are covered by F1b"),
    ("/api/copilot/sessions/{id}", "requires a concrete path parameter value"),
    ("/api/copilot/sessions/{id}/events", "requires a concrete path parameter value"),
    ("/api/copilot/sessions/{id}/events/{eventId}/raw", "file response coverage is deferred to a dedicated fixture"),
    ("/api/copilot/stream", "server-sent events are covered by F1b"),
    ("/api/code-paths/probes/{id}", "requires a concrete path parameter value"),
    ("/api/code-paths/requests/{id}", "requires a concrete path parameter value"),
    ("/api/data/repositories/{name:path}", "requires a concrete path parameter value"),
    ("/api/database-advisor/rules/{rule_id}/violations", "requires a concrete path parameter value"),
    ("/api/database-connection-pools/pools/{name:path}/snapshot", "requires a concrete path parameter value"),
    ("/api/email/{id}", "requires a concrete path parameter value"),
    ("/api/email/{id}/eml", "file response coverage is deferred to a dedicated fixture"),
    ("/api/exceptions/stream", "server-sent events are covered by F1b"),
    ("/api/exceptions/{id}", "requires a concrete path parameter value"),
    ("/api/fastapi/rules/{rule_id}/violations", "requires a concrete path parameter value"),
    ("/api/log-tail/stream", "server-sent events are covered by F1b"),
    ("/api/rest-api/rules/{rule_id}/violations", "requires a concrete path parameter value"),
    ("/api/security-logs/stream", "server-sent events are covered by F1b"),
    ("/api/security/rules/{rule_id}/violations", "requires a concrete path parameter value"),
    ("/api/sql-trace/stream", "server-sent events are covered by F1b"),
    ("/api/traces/{id}", "requires a concrete path parameter value"),
    ("/api/transactions/stream", "server-sent events are covered by F1b"),
)
_DEFERRED_PATHS = {path for path, _reason in DEFERRED}


def test_get_corpus_covers_each_non_deferred_get_route(no_side_effects) -> None:
    state_dir = str(no_side_effects.state_dir)
    with isolated_environment(state_dir):
        assert set(os.environ) <= {
            "HOME",
            "USERPROFILE",
            "TMP",
            "TEMP",
            "SYSTEMROOT",
            "WINDIR",
            "PATH",
            "SHARPIT_TEST_API_TOKEN",
        }
        _assert_get_corpus(no_side_effects)


def _assert_get_corpus(no_side_effects) -> None:
    state_dir = str(no_side_effects.state_dir)
    routes = get_routes(build_app(state_dir=state_dir))
    get_paths = {path for method, path in routes if method == "GET"}
    deferred_paths = {path for path in get_paths if path in _DEFERRED_PATHS}
    expected_paths = get_paths - deferred_paths
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))

    assert set(corpus) == expected_paths
    assert deferred_paths == _DEFERRED_PATHS
    assert get_paths == set(corpus) | deferred_paths
    assert all(len(reason.split()) > 1 for _path, reason in DEFERRED)

    for path in sorted(expected_paths):
        app = build_app(state_dir=state_dir)
        client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
        no_side_effects.unblock_network()
        try:
            with client:
                no_side_effects.block_network()
                try:
                    actual = normalise(record(client, "GET", f"/sharpit{path}"))
                finally:
                    no_side_effects.unblock_network()
        finally:
            no_side_effects.block_network()
        assert_corpus_match(actual, corpus[path], path)
