"""Task 7 CLI commands and executable entry points."""

import io
import subprocess
import sys
from pathlib import Path

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

    def get(self, path):
        self.requests.append(("get", path))
        if path == "/cli":
            return self.catalog()
        return {"serverName": "sharpit", "transport": "http", "enabled": False, "tools": []}

    def post(self, path, body):
        self.requests.append(("post", path, body))
        return {"serverName": "sharpit", "transport": "http", "enabled": True, "tools": []}


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
    from sharpit.cli import fail_on

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
    evaluate = fail_on.evaluate

    def evaluate_after_output(payload, criterion, tool_name):
        assert out.getvalue() == '{"scan":{"status":"SCANNED"},"severityCounts":[{"severity":"HIGH","count":1}]}\n'
        return evaluate(payload, criterion, tool_name)

    monkeypatch.setattr(fail_on, "evaluate", evaluate_after_output)
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


def test_readonly_mcp_toggle_returns_refusal_exit_code():
    class ReadOnlyClient(FakeClient):
        def post(self, path, body):
            from sharpit.cli.client import ClientError

            raise ClientError(
                "sharpit answered HTTP 403: sharpit panel access denied: mcp-server is read-only",
                status=403,
                body='{"error":"sharpit panel access denied","reason":"mcp-server is read-only","panel":"mcp-server"}',
            )

    code, _, err, _ = execute(["mcp", "enable"], client=ReadOnlyClient(None))
    assert code == ExitCodes.REFUSED
    assert "read-only" in err


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
