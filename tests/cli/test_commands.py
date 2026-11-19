"""Tests for sharpit CLI global options and command tree dispatch."""

from __future__ import annotations

import io
from typing import Any

from sharpit.cli.client import ToolResult
from sharpit.cli.commands import main, run
from sharpit.cli.manifest import Manifest
from sharpit.cli.options import GlobalOptions


class FakeClient:
    def __init__(self, options: Any) -> None:
        self.options = options
        self.invocations: list[tuple[str, dict[str, Any]]] = []

    def invoke(self, tool: str, arguments: dict[str, Any]) -> ToolResult:
        self.invocations.append((tool, dict(arguments)))
        return ToolResult(tool_name=tool, status=200, raw_body='{"ok": true}', payload={"ok": True})

    def catalog(self) -> Any:
        return {"enabled": True, "tools": []}

    def get(self, path: str) -> Any:
        return {}


def _run_cli(
    argv: list[str],
    environment: dict[str, str] | None = None,
    terminal: bool = False,
    client: FakeClient | None = None,
) -> tuple[int, str, str, FakeClient]:
    out = io.StringIO()
    err = io.StringIO()
    env = {} if environment is None else dict(environment)
    active_client = client or FakeClient(None)
    code = run(
        argv,
        env,
        terminal,
        out,
        err,
        client_factory=lambda opts: setattr(active_client, "options", opts) or active_client,
    )
    return code, out.getvalue(), err.getvalue(), active_client


# ported: GlobalOptionsTests.acceptsOptionsBeforeOrAfterCommand
def test_global_options_accepted_before_and_after_command():
    # Before command
    code1, out1, _, client1 = _run_cli(
        ["--url", "http://127.0.0.1:9000", "--api-path", "/my/api", "--token", "tok1", "--timeout", "30", "beans"]
    )
    assert code1 == 0
    assert client1.options.base_url == "http://127.0.0.1:9000"
    assert client1.options.api_path == "/my/api"
    assert client1.options.token == "tok1"
    assert client1.options.timeout == 30.0
    assert len(client1.invocations) == 1
    assert client1.invocations[0][0] == "get_beans"

    # After command
    code2, out2, _, client2 = _run_cli(
        ["beans", "--url", "http://127.0.0.1:9001", "--api-path", "/other/api", "--token", "tok2", "--timeout", "45"]
    )
    assert code2 == 0
    assert client2.options.base_url == "http://127.0.0.1:9001"
    assert client2.options.api_path == "/other/api"
    assert client2.options.token == "tok2"
    assert client2.options.timeout == 45.0
    assert len(client2.invocations) == 1
    assert client2.invocations[0][0] == "get_beans"


# ported: GlobalOptionsTests.tokenPrecedence
def test_token_flag_takes_precedence_over_environment():
    code, _, _, client = _run_cli(
        ["--token", "flag-token", "beans"],
        environment={"SHARPIT_TOKEN": "env-token"},
    )
    assert code == 0
    assert client.options.token == "flag-token"


def test_environment_variables_fill_unset_options():
    code, _, _, client = _run_cli(
        ["beans"],
        environment={
            "SHARPIT_URL": "http://127.0.0.1:9999",
            "SHARPIT_API_PATH": "/custom/api",
            "SHARPIT_TOKEN": "env-token",
        },
    )
    assert code == 0
    assert client.options.base_url == "http://127.0.0.1:9999"
    assert client.options.api_path == "/custom/api"
    assert client.options.token == "env-token"


# ported: BootUiClientOptionsTests.aBareHostAndPortIsTreatedAsHttpBecauseThatIsWhatPeopleType
def test_bare_host_and_port_is_normalized():
    code1, _, _, client1 = _run_cli(["--url", "localhost:8184", "beans"])
    assert code1 == 0
    assert client1.options.base_url == "http://localhost:8184"

    code2, _, _, client2 = _run_cli(["--url", ":9000", "beans"])
    assert code2 == 0
    assert client2.options.base_url == "http://localhost:9000"


def test_no_color_environment_honoured():
    opts = GlobalOptions(no_color=False)
    assert opts.color_output(terminal=True, environment={"NO_COLOR": "1"}) is False
    assert opts.color_output(terminal=True, environment={}) is True
    assert opts.color_output(terminal=False, environment={}) is False

    opts_no_color = GlobalOptions(no_color=True)
    assert opts_no_color.color_output(terminal=True, environment={}) is False


def test_timeout_must_be_positive_seconds():
    # <= 0 or not numeric must result in usage error (exit code 1) before any client request
    code1, _, err1, client1 = _run_cli(["--timeout", "0", "beans"])
    assert code1 == 1
    assert len(client1.invocations) == 0
    assert "positive number of seconds" in err1 or "error:" in err1

    code2, _, err2, client2 = _run_cli(["--timeout", "-5", "beans"])
    assert code2 == 1
    assert len(client2.invocations) == 0

    code3, _, err3, client3 = _run_cli(["--timeout", "abc", "beans"])
    assert code3 == 1
    assert len(client3.invocations) == 0


def test_token_never_appears_in_output():
    secret = "super-secret-token-12345"
    code, out, err, client = _run_cli(["--token", secret, "-v", "beans"])
    assert code == 0
    assert secret not in out
    assert secret not in err
    assert secret not in repr(client.options)
    assert secret not in str(client.options)


# ported: CommandTreeTests.everyCommandInTheManifestInvokesTheToolItProjects
def test_every_command_in_the_manifest_invokes_the_tool_it_projects():
    failures: dict[str, str] = {}
    for tool in Manifest.bundled().tools:
        args = list(tool.path)
        if tool.takes_id:
            args.append("some-id")
        if tool.takes_scan_id:
            args.extend(["--scan-id", "scan-1"])

        client = FakeClient(None)
        code, _, err, _ = _run_cli(args, client=client)
        if code != 0 or len(client.invocations) != 1 or client.invocations[0][0] != tool.name:
            failures[tool.command] = f"exit {code}, err: {err.strip()}, calls: {[c[0] for c in client.invocations]}"

    assert not failures, f"commands that did not reach their tool: {failures}"


# ported: CommandTreeTests.everyCommandAcceptsExactlyTheArgumentsItsSchemaDeclares
def test_every_command_accepts_exactly_the_arguments_its_schema_declares():
    failures: dict[str, str] = {}

    def check(tool: Any, flag: str, val: str, supported: bool) -> None:
        args = list(tool.path)
        if tool.takes_id:
            args.append("some-id")
        if tool.takes_scan_id and flag != "--scan-id":
            args.extend(["--scan-id", "scan-1"])
        args.extend([flag, val])

        client = FakeClient(None)
        code, _, _, _ = _run_cli(args, client=client)
        accepted = code == 0
        if accepted != supported:
            failures[f"{tool.command} {flag}"] = (
                "rejected but schema declares it" if supported else "accepted but schema does not"
            )

    for tool in Manifest.bundled().tools:
        check(tool, "--query", "x", tool.takes_query)
        check(tool, "--limit", "3", tool.takes_limit or tool.name == "get_agent_status")
        check(tool, "--scan-id", "scan-1", tool.takes_scan_id)
        check(tool, "--offset", "3", tool.takes_offset)

    assert not failures, f"commands whose flags disagree with schema: {failures}"


# ported: CommandTreeTests.anIdCommandRefusesToRunWithoutOne
def test_an_id_command_refuses_to_run_without_one():
    tool = Manifest.bundled().by_name("get_exception_detail")
    assert tool is not None

    code, _, err, client = _run_cli(list(tool.path))
    assert code == 1
    assert len(client.invocations) == 0
    assert "error:" in err or "required" in err


# ported: CommandTreeTests.aQueryCommandSendsTheFilterItWasGiven
def test_a_query_command_sends_the_filter_it_was_given():
    tool = Manifest.bundled().by_name("get_beans")
    assert tool is not None

    args = list(tool.path) + ["--query", "dataSource"]
    code, _, _, client = _run_cli(args)
    assert code == 0
    assert len(client.invocations) == 1
    assert client.invocations[0] == ("get_beans", {"query": "dataSource"})


# ported: CommandTreeTests.agentStatusAcceptsAnOlderScriptsLimitWithoutSendingIt
def test_agent_status_accepts_an_older_scripts_limit_without_sending_it():
    tool = Manifest.bundled().by_name("get_agent_status")
    assert tool is not None

    args = list(tool.path) + ["--query", "executors", "--limit", "3"]
    code, _, _, client = _run_cli(args)
    assert code == 0
    assert len(client.invocations) == 1
    assert client.invocations[0] == ("get_agent_status", {"query": "executors"})


# ported: CommandTreeTests.agentSensorCommandsSendTheSensorIdAndRequireApproval
def test_agent_sensor_commands_send_the_sensor_id():
    for name in ("enable_agent_sensor", "disable_agent_sensor"):
        tool = Manifest.bundled().by_name(name)
        assert tool is not None
        assert tool.action is True

        args = list(tool.path) + ["security-sinks"]
        code, _, _, client = _run_cli(args)
        assert code == 0
        assert len(client.invocations) == 1
        assert client.invocations[0] == (name, {"id": "security-sinks"})


# ported: CommandTreeTests.advisorCommandsRequireTheScanIdAndForwardEveryPageArgument
def test_advisor_commands_require_the_scan_id_and_forward_every_page_argument():
    for group in ("architecture", "db", "fastapi", "rest-api", "security"):
        # Without scan-id, must refuse before any request
        code_fail, _, err_fail, client_fail = _run_cli([group, "violations", "RULE-1"])
        assert code_fail == 1
        assert len(client_fail.invocations) == 0
        assert "scan-id" in err_fail or "required" in err_fail

        # With all arguments
        code_ok, _, _, client_ok = _run_cli(
            [group, "violations", "RULE-1", "--scan-id", "scan-1", "--offset", "22", "--limit", "7"]
        )
        assert code_ok == 0
        assert len(client_ok.invocations) == 1
        tool_name, args = client_ok.invocations[0]
        assert tool_name == f"get_{group.replace('-', '_')}_rule_violations" or tool_name.endswith("_rule_violations")
        assert args == {"id": "RULE-1", "scanId": "scan-1", "offset": 22, "limit": 7}


# ported: CommandTreeTests.advisorHelpDocumentsRequiredSnapshotAndOffset
def test_advisor_help_documents_required_snapshot_and_offset():
    code, out, err, client = _run_cli(["architecture", "violations", "--help"])
    assert code == 0
    assert len(client.invocations) == 0
    assert "--scan-id" in out
    assert "--offset" in out
    assert "--limit" in out or "-n" in out
    assert "<id>" in out or "id" in out


def test_group_command_without_subcommand_is_usage_error():
    for cmd in ([], ["agent"], ["agent", "sensor"]):
        code, _, err, client = _run_cli(cmd)
        assert code == 1
        assert len(client.invocations) == 0
        assert "usage:" in err


def test_missing_required_scan_id_is_usage_error_before_request():
    code, _, err, client = _run_cli(["architecture", "violations", "--id", "RULE-1"])
    assert code == 1
    assert len(client.invocations) == 0
    assert "scan-id" in err or "required" in err


def test_main_delegates_to_run():
    # Calling main with --help should return 0
    ret = main(["beans", "--help"])
    assert ret == 0
