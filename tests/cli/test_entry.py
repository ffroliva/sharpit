"""Task 7 CLI commands and executable entry points."""

import io
import json
import subprocess
import sys
from pathlib import Path

from sharpit.cli.client import ToolResult
from sharpit.cli.commands import run
from sharpit.cli.exit_codes import ExitCodes


class FakeClient:
    def __init__(self, _options):
        self.requests = []

    def invoke(self, tool, arguments):
        self.requests.append(("invoke", tool, arguments))
        body = '{ "ratio": 1.50, "ok": true }'
        return ToolResult(tool, 200, body, {"ratio": 1.5, "ok": True})

    def catalog(self):
        self.requests.append(("catalog",))
        return {
            "serverName": "sharpit", "enabled": True,
            "tools": [{"name": "new_tool", "panel": "new-panel", "action": False,
                       "arguments": ["query"], "panelEnabled": True, "panelReadOnly": False}],
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
    code = run(argv, {}, out, err, client_factory=lambda _options: chosen)
    return code, out.getvalue(), err.getvalue(), chosen


def test_piped_output_is_json_and_json_flag_preserves_response_verbatim():
    code, out, _, client = execute(["beans"])
    assert code == 0
    assert out == '{ "ratio": 1.50, "ok": true }\n'
    code, out, _, _ = execute(["--json", "beans"])
    assert code == 0
    assert out == '{ "ratio": 1.50, "ok": true }\n'


def test_answer_is_printed_before_fail_on_gate_reads_payload():
    class GateClient(FakeClient):
        def invoke(self, tool, arguments):
            self.requests.append(("invoke", tool, arguments))
            self.payload_read = False
            return ToolResult(tool, 200, '{"findings":[]}', {"findings": []})

    code, out, _, client = execute(["--fail-on", "high", "beans"], client=GateClient(None))
    assert code == ExitCodes.SUCCESS
    assert out == '{"findings":[]}\n'
    assert client.requests[0][0] == "invoke"


def test_tools_lists_target_advertised_catalog_instead_of_bundled_manifest():
    code, out, _, client = execute(["tools"])
    assert code == 0
    assert client.requests[0][0] == "get"
    assert client.requests[0][1] == "/cli"
    assert "new_tool" in out


def test_tool_not_advertised_by_target_exits_one_and_names_tool():
    client = FakeClient(None)
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
    assert client.requests[0] == ("post", "/mcp-server/toggle", '{"enabled":true}')


def test_readonly_mcp_toggle_returns_refusal_exit_code():
    class ReadOnlyClient(FakeClient):
        def post(self, path, body):
            raise __import__("sharpit.cli.client", fromlist=["ClientError"]).ClientError(
                "sharpit panel access denied: mcp-server is read-only"
            )

    code, _, err, _ = execute(["mcp", "enable"], client=ReadOnlyClient(None))
    assert code == ExitCodes.REFUSED
    assert "read-only" in err


def test_cli_imports_without_frameworks():
    script = "import sys; sys.modules['fastapi']=None; sys.modules['starlette']=None; import sharpit.cli"
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0


def test_cli_makes_no_update_check_request():
    code, _, _, client = execute(["beans"])
    assert code == 0
    assert client.requests == [("invoke", "get_beans", {})]


def test_python_module_entrypoint_is_available():
    result = subprocess.run(
        [sys.executable, "-m", "sharpit.cli", "--version"],
        cwd=Path(__file__).parents[2], capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert result.stdout.startswith("sharpit ")
