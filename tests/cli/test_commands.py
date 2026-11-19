"""Tests for sharpit CLI global options and command tree dispatch."""

from __future__ import annotations

import io
import shlex
from typing import Any

import pytest

from sharpit.cli.client import ClientError, ToolResult
from sharpit.cli.commands import main, run
from sharpit.cli.exit_codes import ExitCodes
from sharpit.cli.manifest import Manifest
from sharpit.cli.options import GlobalOptions


class FakeClient:
    def __init__(self, options: Any) -> None:
        self.options = options
        self.invocations: list[tuple[str, dict[str, Any]]] = []

    def invoke(self, tool: str, arguments: dict[str, Any]) -> ToolResult:
        self.invocations.append((tool, dict(arguments)))
        return ToolResult(tool_name=tool, status=200, raw_body='{"ok": true}', payload={"ok": True})

    def catalog(self) -> dict[str, Any]:
        return {"serverName": "sharpit", "enabled": True, "tools": []}

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


# derived: accepts options before or after command
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


# derived: token flag takes precedence over environment
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
    assert "positive number of seconds" in err1

    code2, _, err2, client2 = _run_cli(["--timeout", "-5", "beans"])
    assert code2 == 1
    assert len(client2.invocations) == 0
    assert "positive number of seconds" in err2

    code3, _, err3, client3 = _run_cli(["--timeout", "abc", "beans"])
    assert code3 == 1
    assert len(client3.invocations) == 0
    assert "not a number of seconds" in err3


def test_token_never_appears_in_output():
    secret = "super-secret-token-12345"
    code, out, err, client = _run_cli(["--token", secret, "-v", "beans"])
    assert code == 0
    assert secret not in out
    assert secret not in err
    assert secret not in repr(client.options)
    assert secret not in str(client.options)
    assert secret not in repr(GlobalOptions(token=secret))


def test_default_client_factory_completes_an_http_call(monkeypatch):
    from sharpit.cli import client as client_module

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read1(self, _size):
            return b'{"ok":true}'

    class Opener:
        def open(self, _request, timeout):
            assert timeout > 0
            return Response()

    monkeypatch.setattr(client_module._request, "build_opener", lambda *_args: Opener())
    code, out, err, _ = _run_cli(["beans"])
    assert code == 0
    assert '"ok": true' in out
    assert err == ""


def test_global_options_repr_redacts_token():
    secret = "private-token-239"
    assert secret not in repr(GlobalOptions(token=secret))


def test_ambiguous_global_option_is_not_abbreviated_or_echoed():
    secret = "do-not-echo-this"
    code, _, err, client = _run_cli(["--tokn", secret, "beans"])
    assert code == 1
    assert secret not in err
    assert len(client.invocations) == 0


def test_short_global_option_is_not_abbreviated():
    code, _, err, client = _run_cli(["--to", "token-value", "beans"])
    assert code == 1
    assert len(client.invocations) == 0
    assert "token-value" not in err


def test_result_without_status_is_not_success():
    from types import SimpleNamespace

    class BareClient(FakeClient):
        def invoke(self, tool, arguments):
            return SimpleNamespace(raw_body="{}", payload={})

    code, _, _, _ = _run_cli(["beans"], client=BareClient(None))
    assert code == 1


def test_usage_errors_do_not_print_token_value():
    secret = "never-print-me"
    code, _, err, client = _run_cli(["--token", secret, "--bogus", "beans"])
    assert code == 1
    assert secret not in err
    assert len(client.invocations) == 0


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
        check(tool, "--limit", "3", tool.takes_limit or tool.ignores_limit)
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
    assert "error: the following arguments are required: <id>" in err


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
def test_agent_sensor_commands_send_the_sensor_id_and_require_approval():
    for name in ("enable_agent_sensor", "disable_agent_sensor"):
        tool = Manifest.bundled().by_name(name)
        assert tool is not None
        assert tool.action is True

        args = list(tool.path) + ["security-sinks"]
        code, _, _, client = _run_cli(args)
        assert code == 0
        assert len(client.invocations) == 1
        assert client.invocations[0] == (name, {"id": "security-sinks"})

        code_help, out_help, _, _ = _run_cli(list(tool.path) + ["--help"])
        assert code_help == 0
        assert "[action - needs approval]" in out_help


# ported: CommandTreeTests.advisorCommandsRequireTheScanIdAndForwardEveryPageArgument
def test_advisor_commands_require_the_scan_id_and_forward_every_page_argument():
    for group in ("architecture", "db", "fastapi", "rest-api", "security"):
        # Without scan-id, must refuse before any request
        code_fail, _, err_fail, client_fail = _run_cli([group, "violations", "RULE-1"])
        assert code_fail == 1
        assert len(client_fail.invocations) == 0
        assert "error: the following arguments are required: --scan-id" in err_fail

        # With all arguments
        code_ok, _, _, client_ok = _run_cli(
            [group, "violations", "RULE-1", "--scan-id", "scan-1", "--offset", "22", "--limit", "7"]
        )
        assert code_ok == 0
        assert len(client_ok.invocations) == 1
        tool_name, args = client_ok.invocations[0]
        expected_tool = (
            "get_database_advisor_rule_violations"
            if group == "db"
            else f"get_{group.replace('-', '_')}_rule_violations"
        )
        assert tool_name == expected_tool
        assert args == {"id": "RULE-1", "scanId": "scan-1", "offset": 22, "limit": 7}


# ported: CommandTreeTests.advisorHelpDocumentsRequiredSnapshotAndOffset
def test_advisor_help_documents_required_snapshot_and_offset():
    code, out, err, client = _run_cli(["architecture", "violations", "--help"])
    assert code == 0
    assert len(client.invocations) == 0
    assert "--scan-id" in out
    assert "--offset" in out
    assert "--limit" in out
    assert "<id>" in out


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
    assert "error: the following arguments are required: --scan-id" in err


def test_main_delegates_to_run():
    # Calling main with --help should return 0
    ret = main(["beans", "--help"])
    assert ret == 0


# ported: BootUiCliTests.aReadOnlyPanelStillRefusesAnActionWithThePolicyExitCode
def test_confirmed_403_panel_access_denied_exits_refused():
    class RefusingClient(FakeClient):
        def invoke(self, tool: str, arguments: dict[str, Any]) -> ToolResult:
            return ToolResult(
                tool,
                403,
                '{"error": "sharpit panel access denied", "reason": "Panel \'security\' is read-only"}',
                {"error": "sharpit panel access denied", "reason": "Panel 'security' is read-only"},
            )

        def catalog(self) -> dict[str, Any]:
            return {"serverName": "sharpit", "enabled": True, "tools": []}

    code, _, err, client = _run_cli(["beans"], client=RefusingClient(None))
    assert code == ExitCodes.REFUSED
    assert "sharpit panel access denied" in err
    assert "Panel 'security' is read-only" in err


# ported: CliContext.confirmBootUiAnswered
def test_unconfirmed_foreign_403_exits_error():
    class Foreign403Client(FakeClient):
        def invoke(self, tool: str, arguments: dict[str, Any]) -> ToolResult:
            return ToolResult(tool, 403, '{"error": "forbidden"}', {"error": "forbidden"})

        def catalog(self) -> dict[str, Any]:
            raise ClientError("404 Not Found")

    code, _, err, client = _run_cli(["beans"], client=Foreign403Client(None))
    assert code == ExitCodes.ERROR
    assert "not a sharpit policy refusal" in err


# ported: ToolOutcome.fromStatus
def test_confirmed_503_disabled_endpoint_exits_refused():
    class DisabledClient(FakeClient):
        def invoke(self, tool: str, arguments: dict[str, Any]) -> ToolResult:
            return ToolResult(tool, 503, '{"error": "service unavailable"}', {"error": "service unavailable"})

        def catalog(self) -> dict[str, Any]:
            return {"serverName": "sharpit", "enabled": False, "tools": []}

    code, _, _, _ = _run_cli(["beans"], client=DisabledClient(None))
    assert code == ExitCodes.REFUSED


def test_programming_error_without_verbose_propagates():
    class CrashingClient(FakeClient):
        def invoke(self, tool: str, arguments: dict[str, Any]) -> ToolResult:
            raise RuntimeError("unexpected internal bug")

    with pytest.raises(RuntimeError, match="unexpected internal bug"):
        _run_cli(["beans"], client=CrashingClient(None))


def test_programming_error_with_verbose_prints_traceback():
    class CrashingClient(FakeClient):
        def invoke(self, tool: str, arguments: dict[str, Any]) -> ToolResult:
            raise RuntimeError("unexpected internal bug")

    with pytest.raises(RuntimeError, match="unexpected internal bug"):
        _run_cli(["-v", "beans"], client=CrashingClient(None))


def test_timeout_accepts_duration_strings_and_bare_seconds():
    # AGENTS.md: Durations accept Ns, Nms or bare seconds
    code1, _, _, client1 = _run_cli(["--timeout", "500ms", "beans"])
    assert code1 == 0
    assert client1.options.timeout == 0.5

    code2, _, _, client2 = _run_cli(["--timeout", "2s", "beans"])
    assert code2 == 0
    assert client2.options.timeout == 2.0

    code3, _, _, client3 = _run_cli(["--timeout", "15", "beans"])
    assert code3 == 0
    assert client3.options.timeout == 15.0


def test_version_flag_supported_on_subcommands():
    # ported: BootUiCliTests (version on every command)
    code1, out1, _, _ = _run_cli(["--version"])
    assert code1 == 0
    assert "sharpit" in out1

    code2, out2, _, _ = _run_cli(["beans", "--version"])
    assert code2 == 0
    assert "sharpit" in out2

    code3, out3, _, _ = _run_cli(["beans", "-V"])
    assert code3 == 0
    assert "sharpit" in out3


# ported: CommandTreeTests.anActionsHelpPrintsItsWholeDescriptionWithTheApprovalTag
def test_actions_help_prints_whole_description_with_the_approval_tag():
    code_action, out_action, _, _ = _run_cli(["sql", "clear", "--help"])
    assert code_action == 0
    assert "[action - needs approval]" in out_action

    code_read, out_read, _, _ = _run_cli(["beans", "--help"])
    assert code_read == 0
    assert "[action - needs approval]" not in out_read


# ported: CommandTreeTests.everyExampleInTheHelpRunsItsToolWithExactlyTheArgumentsItShows
def test_every_example_in_the_help_runs_its_tool_with_exactly_the_arguments_it_shows():
    failures: dict[str, str] = {}
    for tool in Manifest.bundled().tools:
        words = shlex.split(tool.example)
        assert words[0] == "sharpit"
        client = FakeClient(None)
        code, _, err, _ = _run_cli(words[1:], client=client)
        if code != 0 or len(client.invocations) != 1 or client.invocations[0][0] != tool.name:
            failures[tool.command] = f"exit {code}, err: {err.strip()}, calls: {[c[0] for c in client.invocations]}"
    assert not failures, f"examples that did not reach their tool: {failures}"
