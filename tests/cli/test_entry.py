"""Task 7 CLI commands and executable entry points."""

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from sharpit import __version__
from sharpit.cli.client import ToolResult
from sharpit.cli.commands import run
from sharpit.cli.exit_codes import ExitCodes


class FakeClient:
    def __init__(self, options):
        self.options = options
        self.requests = []

    def invoke(self, tool, arguments):
        self.requests.append(("invoke", tool, arguments))
        body = '{ "ratio": 1.50, "ok": true }'
        return ToolResult(tool, 200, body, {"ratio": 1.5, "ok": True})

    def catalog(self):
        self.requests.append(("catalog",))
        return {
            "serverName": "sharpit",
            "enabled": True,
            "tools": [
                {
                    "name": "new_tool",
                    "panel": "new-panel",
                    "action": False,
                    "arguments": ["query"],
                    "panelEnabled": True,
                    "panelReadOnly": False,
                }
            ],
        }

    def catalog_result(self):
        from sharpit.cli.client import ToolResult

        payload = self.catalog()
        return ToolResult("/cli", 200, json.dumps(payload), payload)

    def get(self, path):
        self.requests.append(("get", path))
        if path == "/cli":
            return self.catalog()
        return {"serverName": "sharpit", "transport": "http", "enabled": False, "tools": []}

    def get_result(self, path):
        from sharpit.cli.client import ToolResult

        payload = self.get(path)
        return ToolResult(path, 200, json.dumps(payload), payload)

    def post(self, path, body):
        self.requests.append(("post", path, body))
        return {"serverName": "sharpit", "transport": "http", "enabled": True, "tools": []}

    def post_result(self, path, body):
        from sharpit.cli.client import ToolResult

        payload = self.post(path, body)
        return ToolResult(path, 200, json.dumps(payload), payload)


def execute(argv, *, client=None, output=None):
    out, err = output or io.StringIO(), io.StringIO()
    chosen = client or FakeClient(None)
    code = run(argv, {}, False, out, err, client_factory=lambda options: setattr(chosen, "options", options) or chosen)
    return code, out.getvalue(), err.getvalue(), chosen


def test_piped_output_is_json_and_json_flag_preserves_response_verbatim():
    code, out, _, client = execute(["beans"])
    assert code == 0
    assert out == '{ "ratio": 1.50, "ok": true }\n'


def test_terminal_output_uses_readable_renderer_and_honors_no_color():
    out, err, client = io.StringIO(), io.StringIO(), FakeClient(None)
    code = run(
        ["beans"], {}, True, out, err, client_factory=lambda options: setattr(client, "options", options) or client
    )
    assert code == 0
    assert "ratio" in out.getvalue()
    assert "1.50" in out.getvalue()
    assert "\x1b[" in out.getvalue()
    out = io.StringIO()
    code = run(["beans", "--no-color"], {}, True, out, err, client_factory=lambda options: FakeClient(options))
    assert code == 0
    assert "\x1b[" not in out.getvalue()
    out = io.StringIO()
    code = run(["beans"], {"NO_COLOR": "1"}, True, out, err, client_factory=lambda options: FakeClient(options))
    assert code == 0
    assert "\x1b[" not in out.getvalue()
    code, out, _, _ = execute(["--json", "beans"])
    assert code == 0
    assert out == '{ "ratio": 1.50, "ok": true }\n'


def test_answer_is_printed_before_fail_on_gate_reads_payload(monkeypatch):
    from sharpit.cli import commands

    class GateClient(FakeClient):
        def invoke(self, tool, arguments):
            self.requests.append(("invoke", tool, arguments))
            body = '{"scan":{"status":"SCANNED"},"severityCounts":[{"severity":"HIGH","count":1}]}'
            return ToolResult(
                tool,
                200,
                body,
                {"scan": {"status": "SCANNED"}, "severityCounts": [{"severity": "HIGH", "count": 1}]},
            )

    out, err = io.StringIO(), io.StringIO()
    client = GateClient(None)
    evaluate = commands.evaluate

    def evaluate_after_output(payload, criterion, tool_name):
        assert out.getvalue() == '{"scan":{"status":"SCANNED"},"severityCounts":[{"severity":"HIGH","count":1}]}\n'
        return evaluate(payload, criterion, tool_name)

    monkeypatch.setattr(commands, "evaluate", evaluate_after_output)
    code = run(
        ["--fail-on", "high", "security", "scan"],
        {},
        False,
        out,
        err,
        client_factory=lambda options: setattr(client, "options", options) or client,
    )
    assert code == ExitCodes.THRESHOLD, err.getvalue()
    assert out.getvalue() == '{"scan":{"status":"SCANNED"},"severityCounts":[{"severity":"HIGH","count":1}]}\n'
    assert "--fail-on" in err.getvalue()


def test_tools_lists_target_advertised_catalog_instead_of_bundled_manifest():
    code, out, _, client = execute(["tools"])
    assert code == 0
    assert client.requests[0] == ("catalog",)
    assert "new_tool" in out
    assert "get_beans" not in out


def test_tool_not_advertised_by_target_exits_one_and_names_tool():
    client = FakeClient(None)
    client.invoke = lambda tool, arguments: ToolResult(tool, 404, '{"error":"unknown tool"}', {"error": "unknown tool"})
    client.catalog = lambda: {"serverName": "sharpit", "enabled": True, "tools": []}
    code, _, err, _ = execute(["beans"], client=client)
    assert code == ExitCodes.ERROR
    assert "get_beans" in err


def test_mcp_status_and_toggle_use_server_routes():
    code, _, _, client = execute(["mcp", "status"])
    assert code == 0
    assert client.requests[0] == ("get", "/mcp-server")
    code, _, _, client = execute(["mcp", "enable"])
    assert code == 0
    assert client.requests[0] == ("post", "/mcp-server/toggle", '{"enabled": true}')


# ported: BootUiCliTests.directMcpPanelRefusalsPreserveTheirReasonAndExistingErrorExit
def test_readonly_mcp_toggle_returns_refusal_exit_code():
    class ReadOnlyClient(FakeClient):
        def catalog(self):
            self.requests.append(("catalog",))
            return {
                "serverName": "sharpit",
                "enabled": True,
                "tools": [{"name": "mcp_toggle", "panel": "mcp-server", "action": True, "panelReadOnly": True}],
            }

        def post(self, path, body):
            self.requests.append(("post", path, body))
            from sharpit.cli.client import ClientError

            raise ClientError(
                "sharpit answered HTTP 403: sharpit panel access denied: mcp-server is read-only",
                status=403,
                body='{"error":"sharpit panel access denied","reason":"mcp-server is read-only","panel":"mcp-server"}',
            )

    code, _, err, client = execute(["mcp", "enable"], client=ReadOnlyClient(None))
    assert code == ExitCodes.ERROR
    assert "read-only" in err
    assert "(panel 'mcp-server')" not in err
    assert client.requests == [("post", "/mcp-server/toggle", '{"enabled": true}')]


def test_cli_imports_without_frameworks():
    script = "import sys; sys.modules['fastapi']=None; sys.modules['starlette']=None; import sharpit.cli"
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0


def test_non_utf8_output_stream_replaces_unrepresentable_text():
    class AsciiStream(io.StringIO):
        encoding = "ascii"

        def write(self, text):
            text.encode("ascii")
            return super().write(text)

    out, err = AsciiStream(), io.StringIO()

    class UnicodeClient(FakeClient):
        def invoke(self, tool, arguments):
            return ToolResult(tool, 200, '{"message":"café"}', {"message": "café"})

    code = run(["beans"], {}, True, out, err, client_factory=lambda options: UnicodeClient(options))
    assert code == ExitCodes.SUCCESS
    assert "?" in out.getvalue()


def test_cli_makes_no_update_check_request():
    code, _, _, client = execute(["beans"])
    assert code == 0
    assert client.requests == [("invoke", "get_beans", {})]


# ported: BootUiCliTests.helpNeedsNoRunningApplication
def test_builtin_parser_redacts_token_and_writes_help_to_injected_streams(capsys):
    out, err = io.StringIO(), io.StringIO()
    assert run(["mcp", "--tokn", "s3cret-value"], {}, False, out, err) == ExitCodes.ERROR
    assert "s3cret-value" not in err.getvalue()
    assert "s3cret-value" not in capsys.readouterr().err
    out, err = io.StringIO(), io.StringIO()
    assert run(["mcp", "--help"], {}, False, out, err) == ExitCodes.SUCCESS
    assert "usage:" in out.getvalue()


def test_unknown_command_lists_groups_with_readable_metavars():
    out, err = io.StringIO(), io.StringIO()
    assert run(["bogus"], {}, False, out, err) == ExitCodes.ERROR
    assert "tools" in err.getvalue()
    assert "mcp" in err.getvalue()
    assert "_sub_0" not in err.getvalue()
    assert "_mcp_action" not in err.getvalue()


# derived: built-in commands do not accept the tool-only severity gate.
def test_fail_on_is_rejected_for_builtin_commands():
    for argv in (["tools", "--fail-on", "high"], ["mcp", "status", "--fail-on", "critical"]):
        code, _, _, client = execute(argv)
        assert code == ExitCodes.ERROR
        assert client.requests == []
    assert run(["--fail-on", "high", "beans"], {}, False, io.StringIO(), io.StringIO()) == ExitCodes.ERROR


@pytest.mark.parametrize("argv", [["--fail-on", "high", "beans"], ["--fail-on=high", "beans"]])
def test_fail_on_usage_forms_have_the_same_error_exit(argv):
    assert run(argv, {}, False, io.StringIO(), io.StringIO()) == ExitCodes.ERROR


def test_invalid_fail_on_value_has_usage_error_exit():
    assert run(["--fail-on", "not-a-severity", "security", "scan"], {}, False, io.StringIO(), io.StringIO()) == 1


def test_help_and_version_win_over_invalid_fail_on():
    out, err = io.StringIO(), io.StringIO()
    assert run(["--fail-on", "nonsense", "--help"], {}, False, out, err) == ExitCodes.SUCCESS
    assert "usage:" in out.getvalue()
    out, err = io.StringIO(), io.StringIO()
    assert run(["--fail-on", "nonsense", "--version"], {}, False, out, err) == ExitCodes.SUCCESS
    assert out.getvalue() == f"sharpit {__version__}\n"


@pytest.mark.parametrize("json_output", [False, True])
@pytest.mark.parametrize("token,encoded", [(r'ab"c\d', r'ab\"c\\d'), ("é", r"\u00e9"), ("/", r"\/")])
def test_token_escapes_are_redacted_in_final_json_and_terminal_text(json_output, token, encoded):
    body = '{"secret":"' + encoded + '"}'

    class SecretClient(FakeClient):
        def invoke(self, tool, arguments):
            return ToolResult(tool, 200, body, {"secret": token})

    out, err = io.StringIO(), io.StringIO()
    argv = (["--json"] if json_output else []) + ["beans"]
    code = run(argv, {"SHARPIT_TOKEN": token}, True, out, err, client_factory=SecretClient)
    assert code == ExitCodes.SUCCESS
    expected = 'secret: [redacted]\n' if not json_output else '{"secret":"[redacted]"}\n'
    assert out.getvalue() == expected


def test_mcp_status_does_not_construct_manifest_leaf_parsers(monkeypatch):
    from sharpit.cli import commands

    built = []
    configure = commands._configure_leaf_arguments
    monkeypatch.setattr(commands, "_configure_leaf_arguments", lambda parser, tool: built.append(tool.name))
    execute(["mcp", "status"])
    monkeypatch.setattr(commands, "_configure_leaf_arguments", configure)
    assert built == []


def test_mcp_action_hides_transport_error_after_request_was_sent():
    from sharpit.cli.client import ClientError

    class FailingMcpClient(FakeClient):
        def post_result(self, path, body):
            error = ClientError("Cannot reach sharpit")
            error.request_sent = True
            raise error

    code, _, err, _ = execute(["mcp", "enable"], client=FailingMcpClient(None))
    assert code == ExitCodes.ERROR
    assert "outcome is unknown" in err
    assert "Cannot reach" not in err


def test_mcp_action_preserves_transport_error_before_request_was_sent():
    from sharpit.cli.client import ClientError

    class FailedBeforeSendClient(FakeClient):
        def post_result(self, path, body):
            raise ClientError("Cannot reach sharpit", request_sent=False)

    code, _, err, _ = execute(["mcp", "enable"], client=FailedBeforeSendClient(None))
    assert code == ExitCodes.ERROR
    assert "Cannot reach" in err


@pytest.mark.parametrize("command", ["beans", "tools", "mcp status"])
def test_builtin_json_redacts_escaped_token_from_verbatim_body(command):
    from sharpit.cli.client import ToolResult

    token = 'a"b\\c'
    if command == "beans":
        name, body, payload = "get_beans", json.dumps({"secret": token}), {"secret": token}
    elif command == "tools":
        name, payload = "/cli", {"serverName": "sharpit", "enabled": True, "tools": [], "secret": token}
        body = json.dumps(payload)
    else:
        name = "/mcp-server"
        payload = {"serverName": "sharpit", "transport": "http", "enabled": False, "tools": [], "secret": token}
        body = json.dumps(payload)

    class RawClient(FakeClient):
        def invoke(self, tool, arguments):
            return ToolResult(tool, 200, body, payload)

        def catalog_result(self):
            return ToolResult(name, 200, body, payload)

        def get_result(self, path):
            return ToolResult(name, 200, body, payload)

    argv = ["--json", *command.split()]
    out, err, client = io.StringIO(), io.StringIO(), RawClient(None)
    code = run(
        argv,
        {"SHARPIT_TOKEN": token},
        False,
        out,
        err,
        client_factory=lambda options: setattr(client, "options", options) or client,
    )
    assert code == ExitCodes.SUCCESS
    assert token not in out.getvalue()
    assert "[redacted]" in out.getvalue()


def test_main_utf8_piped_json_preserves_unicode_bytes(monkeypatch):
    from sharpit.cli import commands

    raw = io.BytesIO()
    out = io.TextIOWrapper(raw, encoding="cp1252")
    err = io.StringIO()

    class UnicodeClient(FakeClient):
        def invoke(self, tool, arguments):
            body = json.dumps({"message": "数据 😀"}, ensure_ascii=False)
            return ToolResult(tool, 200, body, {"message": "数据 😀"})

    monkeypatch.setattr(commands.sys, "stdout", out)
    monkeypatch.setattr(commands.sys, "stderr", err)
    monkeypatch.setattr(commands, "Client", UnicodeClient)
    assert commands.main(["--json", "beans"]) == ExitCodes.SUCCESS
    out.flush()
    assert raw.getvalue().rstrip(b"\r\n") == '{"message": "数据 😀"}'.encode()


def test_main_broken_pipe_cannot_turn_a_threshold_verdict_into_success(monkeypatch):
    from sharpit.cli import commands

    class Broken:
        encoding = "utf-8"

        def isatty(self):
            return False

        def reconfigure(self, **kwargs):
            pass

        def fileno(self):
            return 1

        def write(self, value):
            raise BrokenPipeError()

        def flush(self):
            pass

    monkeypatch.setattr(commands.sys, "stdout", Broken())
    monkeypatch.setattr(commands.os, "open", lambda *_args, **_kwargs: 123)
    dup_calls = []
    monkeypatch.setattr(commands.os, "dup2", lambda *args: dup_calls.append(args))

    class SuccessClient(FakeClient):
        def invoke(self, tool, arguments):
            return ToolResult(tool, 200, '{"scan":{"status":"SCANNED"},"severityCounts":[{"severity":"HIGH","count":1}]}', {"scan": {"status": "SCANNED"}, "severityCounts": [{"severity": "HIGH", "count": 1}]})

    monkeypatch.setattr(commands, "Client", SuccessClient)
    try:
        code = commands.main(["--fail-on", "high", "security", "scan"])
    except BrokenPipeError:
        code = None
    assert code == ExitCodes.ERROR
    assert dup_calls


def test_main_maps_keyboard_interrupt_to_130(monkeypatch):
    from sharpit.cli import commands

    class Interrupted:
        encoding = "utf-8"

        def isatty(self):
            return False

        def reconfigure(self, **kwargs):
            pass

        def write(self, value):
            raise KeyboardInterrupt()

    monkeypatch.setattr(commands.sys, "stdout", Interrupted())
    try:
        code = commands.main(["--help"])
    except KeyboardInterrupt:
        code = None
    assert code == 130


def test_python_module_entrypoint_is_available():
    result = subprocess.run(
        [sys.executable, "-m", "sharpit.cli", "--version"],
        cwd=Path(__file__).parents[2],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == f"sharpit {__version__}\n"
