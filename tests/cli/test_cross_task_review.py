from __future__ import annotations

import io
import json

from sharpit.cli import commands
from sharpit.cli.client import Client, ClientError, ToolResult
from sharpit.cli.options import ClientOptions


class Fake(Client):
    def __init__(self, options: ClientOptions, status: int, body: str):
        super().__init__(options)
        self.status = status
        self.body = body

    def invoke(self, tool: str, arguments: dict[str, object]) -> ToolResult:
        try:
            payload = json.loads(self.body)
        except ValueError:
            payload = None
        return ToolResult(tool, self.status, self.body, payload)

    def catalog(self) -> dict[str, object]:
        return {"serverName": "sharpit", "enabled": True, "tools": []}


def run(argv: list[str], *, env: dict[str, str] | None = None, status: int = 200, body: str = "{}"):
    out, err = io.StringIO(), io.StringIO()
    code = commands.run(argv, env or {}, True, out, err, lambda options: Fake(options, status, body))
    return code, out.getvalue(), err.getvalue()


def test_long_token_is_redacted_before_table_cell_truncation():
    token = "t" * 64
    body = json.dumps([{"name": "row", "detail": "prefix " + token + " suffix"}])

    _, out, _ = run(["health"], env={"SHARPIT_TOKEN": token}, body=body)

    assert token not in out
    assert "[redacted]" in out


def test_json_redaction_preserves_scalars_and_does_not_change_keys():
    _, out, _ = run(["--json", "health"], env={"SHARPIT_TOKEN": "true"}, body='{"enabled": true, "true": "true"}')

    assert out == '{"enabled": true, "true": "[redacted]"}\n'
    assert json.loads(out) == {"enabled": True, "true": "[redacted]"}
    assert '"true"' in out


def test_json_number_is_not_changed_by_short_token():
    _, out, _ = run(["--json", "health"], env={"SHARPIT_TOKEN": "12"}, body='{"count":1234}')

    assert out == '{"count":1234}\n'
    assert json.loads(out) == {"count": 1234}


def test_server_text_and_bootui_url_are_not_rewritten():
    _, out, _ = run(["--json", "health"], body='{"message":"loaded bootui.yml from BootUI"}')

    assert out.strip() == '{"message":"loaded bootui.yml from BootUI"}'
    out, err = io.StringIO(), io.StringIO()
    code = commands.run(["--url", "http://bootui.localhost:9", "health"], {}, True, out, err)
    assert code == 1
    assert "http://bootui.localhost:9" in err.getvalue()


def test_json_escaped_unicode_token_is_redacted_after_decoding():
    _, out, _ = run(
        ["--json", "health"], env={"SHARPIT_TOKEN": "BootUI-secret"}, body='{"secret":"Boot\\u0055I-secret"}'
    )

    assert "Boot" not in out
    assert json.loads(out) == {"secret": "[redacted]"}


def test_server_error_controls_are_sanitized_before_stderr():
    _, _, err = run(["health"], status=500, body='{"message":"oops\\u001b]0;title\\u0007\\u001b[2J"}')

    assert "\x1b" not in err
    assert "\x07" not in err


def test_listed_tool_404_uses_bootui_unknown_tool_description():
    _, _, err = run(["insights", "show", "nosuch"], status=404, body='{"message":"No observation found"}')

    assert "This application does not expose 'get_runtime_insight'." in err
    assert "Only " in err
    assert "No observation found" not in err


def test_usage_errors_only_redact_token_flag_values():
    cases = (
        (["-x", "a", "health"], "a"),
        (["health", "extra-word", "foo"], "foo"),
        (["exceptions", "list", "--fail-on", "high"], "high"),
    )
    for argv, visible in cases:
        _, _, err = run(argv)
        assert visible in err


def test_misspelled_and_case_insensitive_token_flags_redact_values():
    for flag in ("--tokn", "--Token"):
        _, _, err = run([flag, "s3cret", "health"])
        assert "s3cret" not in err
        assert "[redacted]" in err


def test_get_exceptions_fail_on_reports_excluded_reason():
    code, _, err = run(["exceptions", "list", "--fail-on", "high"])

    assert code == 1
    assert "sharpit records no caught-in-code evidence" in err


def test_expired_deadline_never_sets_socket_nonblocking(monkeypatch):
    client = Client(ClientOptions(timeout=1))
    calls: list[float] = []

    class Sock:
        def settimeout(self, value: float) -> None:
            calls.append(value)

    class Response:
        status = 200
        fp = type("FP", (), {"raw": type("Raw", (), {"_sock": Sock()})()})()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b"{}"

    monkeypatch.setattr(client, "_open_response", lambda *args: Response())
    class Thread:
        def __init__(self, *, target, daemon):
            self.target = target

        def start(self):
            self.target()

        def join(self, timeout=None):
            return None

        def is_alive(self):
            return False

    monkeypatch.setattr("sharpit.cli.client.threading.Thread", Thread)
    monkeypatch.setattr("sharpit.cli.client.time.monotonic", lambda: 1.0)

    try:
        client._exchange(object(), 0.5, "http://localhost:8000")
    except ClientError as error:
        assert "within 1s" in str(error)
    else:
        raise AssertionError("expected the expired deadline to time out")

    assert 0.0 not in calls


def test_latin1_token_is_redacted_from_error_body(monkeypatch):
    token = "secrét123456"
    client = Client(ClientOptions(token=token))
    monkeypatch.setattr(client, "_exchange", lambda *args: (500, token.encode("latin-1")))

    try:
        client._send("http://localhost:8000/sharpit/api/health", "GET", None)
    except ClientError as error:
        assert token not in error.body
        assert "[redacted]" in error.body
    else:
        raise AssertionError("expected the error response")


def test_503_message_has_no_duplicate_status_suffix():
    _, _, err = run(["health"], status=503, body='{"message":"Service unavailable (HTTP 503)"}')

    assert err.count("HTTP 503") == 1


def test_action_and_mcp_refusal_exit_codes_are_documented():
    from pathlib import Path

    root = Path(__file__).parents[2]
    readme = (root / "README.md").read_text()
    skill = (root / "skills/sharpit/SKILL.md").read_bytes()
    plugin_skill = (root / "plugins/sharpit/skills/sharpit/SKILL.md").read_bytes()

    assert "`2`: refused tool action" in readme
    assert "`1`: refused MCP toggle" in readme
    assert b"`2`: refused tool action" in skill
    assert b"`1`: refused MCP toggle" in skill
    assert skill == plugin_skill

