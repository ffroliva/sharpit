from __future__ import annotations

import io
import json

import pytest

from sharpit.cli import commands
from sharpit.cli.client import Client, ClientError, ToolResult
from sharpit.cli.options import ClientOptions


class _DeadlineSocket:
    def __init__(self) -> None:
        self.timeouts: list[float] = []

    def settimeout(self, value: float) -> None:
        self.timeouts.append(value)


class _DeadlineResponse:
    status = 200

    def __init__(self, sock: _DeadlineSocket) -> None:
        self.fp = type("FP", (), {"raw": type("Raw", (), {"_sock": sock})()})()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return b"{}"


class _ImmediateThread:
    def __init__(self, *, target, daemon):
        self.target = target

    def start(self):
        self.target()

    def join(self, timeout=None):
        return None

    def is_alive(self):
        return False


class Fake(Client):
    def __init__(self, options: ClientOptions, status: int, body: str, tools: list[dict[str, str]] | None = None):
        super().__init__(options)
        self.status = status
        self.body = body
        self.tools = tools or []

    def invoke(self, tool: str, arguments: dict[str, object]) -> ToolResult:
        try:
            payload = json.loads(self.body)
        except ValueError:
            payload = None
        return ToolResult(tool, self.status, self.body, payload)

    def catalog(self) -> dict[str, object]:
        return {"serverName": "sharpit", "enabled": True, "tools": self.tools}

    def get(self, path: str) -> object:
        return {"panels": []}


def run(
    argv: list[str],
    *,
    env: dict[str, str] | None = None,
    status: int = 200,
    body: str = "{}",
    tools: list[dict[str, str]] | None = None,
):
    out, err = io.StringIO(), io.StringIO()
    code = commands.run(argv, env or {}, True, out, err, lambda options: Fake(options, status, body, tools))
    return code, out.getvalue(), err.getvalue()


def test_long_token_is_redacted_before_table_cell_truncation():
    token = "t" * 64
    body = json.dumps([{"name": "row", "detail": "prefix " + token + " suffix"}])

    _, out, _ = run(["health"], env={"SHARPIT_TOKEN": token}, body=body)

    assert token not in out
    assert "[redacted]" in out


def test_json_redaction_preserves_boolean_and_redacts_matching_string_keys_and_values():
    _, out, _ = run(["--json", "health"], env={"SHARPIT_TOKEN": "true"}, body='{"enabled": true, "true": "true"}')

    assert out == '{"enabled": true, "[redacted]": "[redacted]"}\n'
    assert json.loads(out) == {"enabled": True, "[redacted]": "[redacted]"}


def test_json_number_containing_token_is_redacted():
    _, out, _ = run(["--json", "health"], env={"SHARPIT_TOKEN": "12"}, body='{"count":1234}')

    assert out == '{"count":"[redacted]"}\n'
    assert json.loads(out) == {"count": "[redacted]"}


def test_terminal_render_redacts_numeric_literals_and_mapping_keys():
    _, out, _ = run(["health"], env={"SHARPIT_TOKEN": "12"}, body='[{"count":1234}]')

    assert "[redacted]" in out
    assert "1234" not in out

    _, table_out, _ = run(["health"], env={"SHARPIT_TOKEN": "s3cret"}, body='[{"s3cret": "value"}]')

    assert "s3cret" not in table_out


def test_json_short_word_token_redacts_keys_and_values_but_keeps_other_bytes():
    body = '{"dev":"key","environment":"dev","enabled":true}'
    _, out, _ = run(["--json", "health"], env={"SHARPIT_TOKEN": "dev"}, body=body)

    assert out == '{"[redacted]":"key","environment":"[redacted]","enabled":true}\n'
    assert json.loads(out) == {"[redacted]": "key", "environment": "[redacted]", "enabled": True}


def test_json_redaction_preserves_unmatched_escape_and_unicode_spelling():
    body = r'{"message":"\/ \u0041 数据 s3cret"}'
    _, out, _ = run(["--json", "health"], env={"SHARPIT_TOKEN": "s3cret"}, body=body)

    assert out == r'{"message":"\/ \u0041 数据 [redacted]"}' + "\n"


def test_json_number_containing_token_becomes_redacted_string():
    _, out, _ = run(["--json", "health"], env={"SHARPIT_TOKEN": "12"}, body='{"count":1234}')

    assert out == '{"count":"[redacted]"}\n'


def test_invalid_json_always_gets_plain_text_redaction():
    _, out, _ = run(
        ["--json", "health"], env={"SHARPIT_TOKEN": "s3cret"}, body='Bearer s3cret rejected; token="s3cret"'
    )

    assert "s3cret" not in out
    assert 'Bearer [redacted] rejected; token="[redacted]"' in out


def test_server_text_and_bootui_url_are_not_rewritten():
    _, out, _ = run(["--json", "health"], body='{"message":"loaded bootui.yml from BootUI"}')

    assert out.strip() == '{"message":"loaded bootui.yml from BootUI"}'
    out, err = io.StringIO(), io.StringIO()
    code = commands.run(["--url", "http://bootui.localhost:9", "health"], {}, True, out, err)
    assert code == 1
    assert err.getvalue() == (
        "Cannot reach sharpit at http://bootui.localhost:9. Is the application running, and is that the right --url?\n"
    )


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


def test_terminal_json_escapes_raw_c1_controls_but_piped_json_is_verbatim():
    body = '{\n\t"message":"a\u009bb"\n}'
    _, terminal_out, _ = run(["--json", "health"], body=body)
    out, err = io.StringIO(), io.StringIO()
    commands.run(["--json", "health"], {}, False, out, err, lambda options: Fake(options, 200, body))

    assert r"\u009b" in terminal_out
    assert "\n\t" in terminal_out
    assert "\u009b" in out.getvalue()
    assert "a\u009bb" in out.getvalue()
    assert json.loads(terminal_out) == {"message": "a\u009bb"}


def test_usage_messages_escape_terminal_controls_from_argv():
    payload = "\x1b]0;owned\x07"
    _, _, err = run(["health", payload])

    assert "\x1b" not in err
    assert "\x07" not in err
    assert "\\x1b]0;owned\\x07" in err


def test_invalid_timeout_message_escapes_controls_from_argv():
    payload = "\x1b[2J"
    _, _, err = run(["--timeout", payload, "health"])

    assert "\x1b" not in err
    assert "\\x1b[2J" in err


def test_verbose_traceback_keeps_line_breaks():
    class CrashingClient(Fake):
        def invoke(self, tool: str, arguments: dict[str, object]) -> ToolResult:
            raise RuntimeError("boom")

    out, err = io.StringIO(), io.StringIO()
    commands.run(["-v", "health"], {}, True, out, err, lambda options: CrashingClient(options, 200, "{}"))

    assert "Traceback (most recent call last):\n" in err.getvalue()


# derived: CliContext.confirmBootUiAnswered, describe, and unknownToolHint
def test_listed_tool_404_uses_bootui_unknown_tool_description():
    code, _, err = run(
        ["insights", "show", "nosuch"],
        status=404,
        body='{"message":"No observation found"}',
        tools=[{"name": "get_runtime_insight"}],
    )

    assert "No observation found" in err
    assert "This application does not expose" not in err
    assert code == 1


def test_listed_tool_404_error_message_redacts_token_and_does_not_fetch_panels():
    class CountingClient(Fake):
        calls: list[str]

        def __init__(self, options, status, body, tools=None):
            super().__init__(options, status, body, tools)
            self.calls = []

        def invoke(self, tool, arguments):
            self.calls.append("tool")
            return super().invoke(tool, arguments)

        def catalog(self):
            self.calls.append("catalog")
            return super().catalog()

        def get(self, path):
            self.calls.append(path)
            return super().get(path)

    client = None

    def factory(options):
        nonlocal client
        client = CountingClient(options, 404, '{"message":"missing s3cret"}', [{"name": "get_runtime_insight"}])
        return client

    out, err = io.StringIO(), io.StringIO()
    code = commands.run(["--token", "s3cret", "insights", "show", "nosuch"], {}, True, out, err, factory)

    assert code == 1
    assert "s3cret" not in err.getvalue()
    assert client is not None
    assert client.calls == ["tool", "catalog"]


def test_listed_tool_404_outcome_redacts_error_message_with_client_token():
    from sharpit.cli.outcomes import confirm_answered

    client = Fake(ClientOptions(token="s3cret"), 404, '{"message":"missing s3cret"}', [{"name": "get_runtime_insight"}])
    outcome = confirm_answered(client, client.invoke("get_runtime_insight", {}))

    assert "s3cret" not in outcome.message
    assert "missing [redacted]" in outcome.message


def test_unlisted_tool_404_says_the_application_does_not_expose_it():
    _, _, err = run(["insights", "show", "nosuch"], status=404, body='{"message":"Unknown tool"}')

    assert "This application does not expose 'get_runtime_insight'." in err
    assert "older sharpit version" in err


def test_unlisted_tool_404_hint_uses_local_metadata_without_panel_request():
    class CountingClient(Fake):
        def __init__(self, options):
            super().__init__(options, 404, '{"message":"Unknown tool"}')
            self.paths = []

        def get(self, path):
            self.paths.append(path)
            return super().get(path)

    client = None

    def factory(options):
        nonlocal client
        client = CountingClient(options)
        return client

    out, err = io.StringIO(), io.StringIO()
    commands.run(["insights", "show", "nosuch"], {}, True, out, err, factory)

    assert client is not None
    assert client.paths == []


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


@pytest.mark.parametrize(
    "argv,secret",
    [
        (["health", "--tokn=s3cret"], "s3cret"),
        (["health", "--TOKEN=s3cret"], "s3cret"),
        (["health", "--access-token", "s3cret"], "s3cret"),
        (["health", "--bearer", "s3cret"], "s3cret"),
        (["health", "--api-key=s3cret"], "s3cret"),
        (["health", "--tokn", "-Xy9secret"], "-Xy9secret"),
    ],
)
def test_token_like_option_values_are_redacted_even_at_argv_end(argv, secret):
    _, _, err = run(argv)

    assert secret not in err
    assert "[redacted]" in err


def test_get_exceptions_fail_on_reports_excluded_reason():
    code, _, err = run(["exceptions", "list", "--fail-on", "high"])

    assert code == 1
    assert "sharpit records no caught-in-code evidence" in err


def test_expired_deadline_never_sets_socket_nonblocking(monkeypatch):
    client = Client(ClientOptions(timeout=1))
    sock = _DeadlineSocket()
    monkeypatch.setattr(client, "_open_response", lambda *args: _DeadlineResponse(sock))
    monkeypatch.setattr("sharpit.cli.client.threading.Thread", _ImmediateThread)
    monkeypatch.setattr("sharpit.cli.client.time.monotonic", lambda: 1.0)

    with pytest.raises(ClientError, match="within 1s"):
        client._exchange(object(), 0.5, "http://localhost:8000")

    assert 0.0 not in sock.timeouts


def test_latin1_token_is_redacted_from_error_body(monkeypatch):
    token = "secrét123456"
    client = Client(ClientOptions(token=token))
    body = f'{{"message":"{token}"}}'.encode("latin-1")
    monkeypatch.setattr(client, "_exchange", lambda *args: (500, body))
    status, body = client._send("http://localhost:8000/sharpit/api/health", "GET", None)
    error = client._describe_failure(status, body)

    assert token not in error.body
    assert "[redacted]" in error.body


# ported: BootUiCliTests.anUnrelatedUnavailableServerIsAnErrorNotAConfigurationSkip
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
    assert "refused MCP toggle exits 1" in readme
    assert b"`2` (`REFUSED`): refused tool action" in skill
    assert b"refused MCP toggle exits 1" in skill
    assert skill == plugin_skill
