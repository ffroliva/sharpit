"""Command tree and CLI dispatch for sharpit (BootUI's CommandTree and BootUiCli)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any, NoReturn, TextIO, cast

from sharpit import __version__
from sharpit.cli.arguments import build_tool_arguments
from sharpit.cli.client import Client, ClientError, ToolResult, safe_text
from sharpit.cli.exit_codes import ExitCodes
from sharpit.cli.fail_on import Criterion, evaluate
from sharpit.cli.fail_on import parse as parse_fail_on
from sharpit.cli.manifest import Manifest, ManifestTool
from sharpit.cli.options import ClientOptions, GlobalOptions, normalize_token, positive_seconds
from sharpit.cli.outcomes import OutcomeKind, confirm_answered
from sharpit.cli.render import render, write

__all__ = ["main", "run"]

_ACTION_TAG = "[action - needs approval]"
_KNOWN_OPTIONS = frozenset(
    {
        "--url",
        "--api-path",
        "--token",
        "--timeout",
        "--json",
        "--fail-on",
        "--no-color",
        "--verbose",
        "-v",
        "--version",
        "-V",
        "--help",
        "-h",
        "--query",
        "-q",
        "--limit",
        "-n",
        "--id",
        "--scan-id",
        "--offset",
    }
)


class _CliExit(Exception):
    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(status)


def _redact_usage_error(message: str, tokens: Sequence[str] = ()) -> str:
    msg = message
    if "unrecognized arguments:" in message:
        msg = re.sub(r"(?i)(-{1,2}[^\s=]+\s+)[^\s]+", r"\1[redacted]", msg)
        msg = re.sub(r"(?i)(-{1,2}[^\s=]+=)[^\s]+", r"\1[redacted]", msg)
    for token in tokens:
        if token:
            msg = msg.replace(token, "[redacted]")
    return msg


class SharpitParser(argparse.ArgumentParser):
    """An ArgumentParser that writes to custom streams and never exits the process."""

    def __init__(
        self,
        *args: Any,
        out: TextIO | None = None,
        err: TextIO | None = None,
        **kwargs: Any,
    ) -> None:
        kwargs["allow_abbrev"] = False
        kwargs.setdefault("formatter_class", argparse.RawDescriptionHelpFormatter)
        super().__init__(*args, **kwargs)
        self.out: TextIO | None = out
        self.err: TextIO | None = err
        self.tokens: tuple[str, ...] = ()

    def set_streams(self, out: TextIO | None, err: TextIO | None) -> None:
        self.out = out
        self.err = err

    def _print_message(self, message: str, file: Any = None) -> None:
        target = self.out if file is None or file is sys.stdout or file is self.out else self.err or file
        if target is not None:
            write(target, message)
            if hasattr(target, "flush"):
                target.flush()
        else:
            super()._print_message(message, file)

    def exit(self, status: int = 0, message: str | None = None) -> NoReturn:
        if message:
            self._print_message(message, sys.stderr)
        raise _CliExit(status)

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        sanitized = _redact_usage_error(message, self.tokens)
        self.exit(ExitCodes.ERROR, f"{self.prog}: error: {sanitized}\n")


TEXT_METAVAR = "<text>"


def _create_globals_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument(
        "--url",
        default=argparse.SUPPRESS,
        metavar=TEXT_METAVAR,
        help="The application's base URL (SHARPIT_URL; default: http://localhost:8000)",
    )
    parser.add_argument(
        "--api-path",
        default=argparse.SUPPRESS,
        metavar=TEXT_METAVAR,
        help="The sharpit API path (SHARPIT_API_PATH; default: /sharpit/api)",
    )
    parser.add_argument(
        "--token",
        default=argparse.SUPPRESS,
        metavar="<token>",
        help="Authentication bearer token (SHARPIT_TOKEN)",
    )
    parser.add_argument(
        "--timeout",
        type=positive_seconds,
        default=argparse.SUPPRESS,
        metavar="<seconds>",
        help="Request timeout in seconds (default: 60)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Print the application's JSON verbatim",
    )
    parser.add_argument(
        "--fail-on",
        default=argparse.SUPPRESS,
        metavar="<severity>",
        help="Exit 3 at or above this severity",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Disable ANSI color",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Print verbose error details",
    )
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"sharpit {__version__}",
        help="Show program's version number and exit",
    )
    return parser


def _configure_leaf_arguments(leaf_parser: SharpitParser, tool: ManifestTool) -> None:
    desc = f"{_ACTION_TAG} {tool.description}" if tool.action else tool.description
    leaf_parser.description = desc
    leaf_parser.formatter_class = argparse.RawDescriptionHelpFormatter
    leaf_parser.epilog = f"Example: {tool.example}\nMCP tool: {tool.name}"
    leaf_parser.set_defaults(_tool=tool, _leaf_parser=leaf_parser)

    if tool.takes_query:
        leaf_parser.add_argument("-q", "--query", default=None, metavar=TEXT_METAVAR, help="Filter results")
    if tool.takes_limit or tool.ignores_limit:
        help_text = "Return at most this many results" if tool.takes_limit else argparse.SUPPRESS
        leaf_parser.add_argument("-n", "--limit", type=int, default=None, metavar="<count>", help=help_text)
    if tool.takes_id:
        required = "id" in tool.required or tool.schema in ("ID", "RULE_VIOLATIONS")
        group = leaf_parser.add_mutually_exclusive_group(required=required)
        identifier_help = "Identifier (required; choose one form)" if required else "Identifier"
        group.add_argument("pos_id", nargs="?", default=None, metavar="<id>", help=identifier_help)
        group.add_argument("--id", dest="flag_id", default=None, metavar="<id>", help=identifier_help)
    if tool.takes_scan_id:
        leaf_parser.add_argument(
            "--scan-id", dest="scan_id", default=None, required=True, metavar="<scanId>", help="Scan ID"
        )
    if tool.takes_offset:
        leaf_parser.add_argument("--offset", type=int, default=None, metavar="<count>", help="Offset")


def _build_root_parser(
    manifest: Manifest, selected_path: tuple[str, ...] | None = None
) -> tuple[SharpitParser, list[SharpitParser]]:
    globals_parser = _create_globals_parser()
    root = SharpitParser(
        prog="sharpit",
        description="Ask a running sharpit application a question.",
        parents=[globals_parser],
    )
    all_parsers: list[SharpitParser] = [root]
    parsers_by_prefix: dict[tuple[str, ...], SharpitParser] = {(): root}
    subparsers_by_prefix: dict[tuple[str, ...], Any] = {}

    def get_or_create_subparsers(prefix: tuple[str, ...]) -> Any:
        if prefix not in subparsers_by_prefix:
            subparsers_by_prefix[prefix] = parsers_by_prefix[prefix].add_subparsers(
                dest=f"_sub_{len(prefix)}",
            )
        return subparsers_by_prefix[prefix]

    specs = manifest.command_specs
    selected = (
        (tool for path, tool in specs if path[: len(selected_path)] == selected_path)
        if selected_path is not None
        else (tool for _, tool in specs)
    )
    for tool in selected:
        path = tool.path
        for depth in range(len(path) - 1):
            prefix = path[:depth]
            word = path[depth]
            child_prefix = (*prefix, word)
            if child_prefix not in parsers_by_prefix:
                sub = get_or_create_subparsers(prefix)
                group: SharpitParser = sub.add_parser(word, parents=[globals_parser], allow_abbrev=False)
                group.set_defaults(_group_parser=group)
                parsers_by_prefix[child_prefix] = group
                all_parsers.append(group)

        parent_prefix = path[:-1]
        leaf_word = path[-1]
        leaf_sub = get_or_create_subparsers(parent_prefix)
        leaf_parser: SharpitParser = leaf_sub.add_parser(
            leaf_word, parents=[globals_parser], allow_abbrev=False, help=tool.summary
        )
        _configure_leaf_arguments(leaf_parser, tool)
        all_parsers.append(leaf_parser)

    root_sub = get_or_create_subparsers(())
    tools_parser: SharpitParser = root_sub.add_parser("tools", parents=[globals_parser], allow_abbrev=False)
    tools_parser.set_defaults(_builtin="tools")
    mcp_parser: SharpitParser = root_sub.add_parser("mcp", parents=[globals_parser], allow_abbrev=False)
    mcp_sub = mcp_parser.add_subparsers(dest="_mcp_action")
    for action in ("status", "enable", "disable"):
        leaf: SharpitParser = mcp_sub.add_parser(action, parents=[cast(Any, globals_parser)], allow_abbrev=False)
        leaf.set_defaults(_builtin=f"mcp:{action}")

    return root, all_parsers


def _get_root_parser(
    manifest: Manifest,
    out: TextIO,
    err: TextIO,
    tokens: Sequence[str] = (),
    selected_path: tuple[str, ...] | None = None,
) -> SharpitParser:
    root, parsers = _build_root_parser(manifest, selected_path)
    for parser in parsers:
        parser.set_streams(out, err)
        parser.tokens = tuple(tokens)
    return root


def _usage_tokens(argv: Sequence[str], environment: Mapping[str, str]) -> tuple[str, ...]:
    raw_environment_token = environment.get("SHARPIT_TOKEN", "")
    tokens = [raw_environment_token, normalize_token(raw_environment_token) or ""]
    for index, value in enumerate(argv[:-1]):
        option, separator, attached = value.partition("=")
        if value == "--token":
            tokens.extend((argv[index + 1], normalize_token(argv[index + 1]) or ""))
        elif option == "--token" and separator:
            tokens.extend((attached, normalize_token(attached) or ""))
        elif value.startswith("-") and value not in _KNOWN_OPTIONS:
            if separator:
                tokens.append(attached)
            elif not argv[index + 1].startswith("-"):
                tokens.append(argv[index + 1])
    return tuple(tokens)


def _selected_path(argv: Sequence[str], manifest: Manifest) -> tuple[str, ...] | None:
    candidates = tuple(
        value
        for index, value in enumerate(argv)
        if not value.startswith("-")
        and (index == 0 or argv[index - 1] not in {"--url", "--api-path", "--token", "--timeout", "--fail-on"})
    )
    known_paths = {path for path, _ in manifest.command_specs}
    if candidates and candidates[0] in {"tools", "mcp"}:
        return None
    path = next(
        (candidates[:length] for length in range(len(candidates), 0, -1) if candidates[:length] in known_paths),
        None,
    )
    if path is None and candidates and "--help" not in argv and "-h" not in argv:
        return candidates[:1]
    return path


def _emit_error(err: TextIO, message: str, token: str | None) -> None:
    message = safe_text(message, token)
    write(err, message)
    if not message.endswith("\n"):
        write(err, "\n")
    if hasattr(err, "flush"):
        err.flush()


def _emit_client_error(err: TextIO, error: ClientError, token: str | None, verbose: bool) -> None:
    _emit_error(err, str(error), token)
    if verbose and error.__cause__ is not None:
        import traceback

        write(err, safe_text("".join(traceback.format_exception(error)), token))


def _emit_unexpected_error(err: TextIO, error: Exception, token: str | None, verbose: bool) -> None:
    if verbose:
        import traceback

        message = "".join(traceback.format_exception(error))
    else:
        message = " ".join(str(error).splitlines())
    _emit_error(err, message, token)


def _extract_global_options(namespace: argparse.Namespace) -> GlobalOptions:
    return GlobalOptions(
        url=getattr(namespace, "url", None),
        api_path=getattr(namespace, "api_path", None),
        token=getattr(namespace, "token", None),
        timeout=getattr(namespace, "timeout", None),
        json=getattr(namespace, "json", False),
        no_color=getattr(namespace, "no_color", False),
        verbose=getattr(namespace, "verbose", False),
    )


def _usage_error(leaf: SharpitParser, err: TextIO, missing: str) -> None:
    leaf.print_usage(err)
    err.write(f"{leaf.prog}: error: the following arguments are required: {missing}\n")


def _identifier(namespace: argparse.Namespace) -> object | None:
    flag_id = getattr(namespace, "flag_id", None)
    return flag_id if flag_id is not None else getattr(namespace, "pos_id", None)


def _extract_tool_args(
    namespace: argparse.Namespace,
    tool: ManifestTool,
    root_parser: SharpitParser,
    err: TextIO,
    criterion: Criterion | None = None,
) -> dict[str, Any] | None:
    leaf = getattr(namespace, "_leaf_parser", root_parser)
    args_payload: dict[str, Any] = {}
    identifiers = (
        (tool.takes_id, "id", _identifier(namespace), "<id>", tool.schema in ("ID", "RULE_VIOLATIONS")),
        (
            tool.takes_scan_id,
            "scanId",
            getattr(namespace, "scan_id", None),
            "--scan-id",
            tool.schema == "RULE_VIOLATIONS",
        ),
    )
    for takes, wire, value, shown, schema_requires in identifiers:
        if not takes:
            continue
        if value is not None:
            args_payload[wire] = value
        elif wire in tool.required or schema_requires:
            _usage_error(leaf, err, shown)
            return None
    for takes, name in ((tool.takes_offset, "offset"), (tool.takes_limit, "limit"), (tool.takes_query, "query")):
        if takes and (value := getattr(namespace, name, None)) is not None:
            args_payload[name] = value
    return build_tool_arguments(tool, args_payload, criterion)


def _call_client(
    factory: Callable[[ClientOptions], Client],
    client_options: ClientOptions,
    tool_name: str,
    args_payload: dict[str, Any],
    err: TextIO,
    verbose: bool,
) -> tuple[Client, ToolResult] | None:
    try:
        client = factory(client_options)
        result = client.invoke(tool_name, args_payload)
    except ClientError as exc:
        _emit_client_error(err, exc, client_options.token, verbose)
        return None
    except Exception as exc:
        _emit_unexpected_error(err, exc, client_options.token, verbose)
        return None

    if type(result) is not ToolResult or not isinstance(getattr(result, "status", None), int):
        _emit_error(err, "Client returned an invalid tool result", client_options.token)
        return None
    return client, result


def _emit_result(
    client: Client,
    result: ToolResult,
    client_options: ClientOptions,
    tool: ManifestTool,
    out: TextIO,
    err: TextIO,
    verbose: bool,
    json_output: bool,
    terminal: bool,
    color: bool,
    environment: Mapping[str, str],
    criterion: Criterion | None,
) -> int:
    try:
        outcome = confirm_answered(client, result)
    except ClientError as exc:
        _emit_client_error(err, exc, client_options.token, verbose)
        return ExitCodes.ERROR

    if outcome.kind is OutcomeKind.SUCCESS:
        return _emit_success_result(result, client_options, tool, out, err, json_output, terminal, color, criterion)

    message = outcome.message
    if outcome.kind is OutcomeKind.ENDPOINT_DISABLED:
        message = (
            "The sharpit command-line endpoint is disabled on this application. Set SHARPIT_CLI_ENABLED=ON to allow it."
        )
    elif outcome.kind is OutcomeKind.UNKNOWN_TOOL:
        message = f"This application does not expose '{tool.name}'."
    elif outcome.kind is OutcomeKind.UNAUTHENTICATED:
        message += (
            ". A non-loopback --url needs --token or SHARPIT_TOKEN, "
            "and sharpit only answers requests it considers local."
        )
    elif outcome.kind is OutcomeKind.REFUSED_BY_POLICY:
        message += f" (panel '{tool.panel}')"
    _emit_error(err, message, client_options.token)
    return outcome.exit_code


def _emit_success_result(
    result: ToolResult,
    client_options: ClientOptions,
    tool: ManifestTool,
    out: TextIO,
    err: TextIO,
    json_output: bool,
    terminal: bool,
    color: bool,
    criterion: Criterion | None,
) -> int:
    body = result.raw_body or (json.dumps(result.payload) if result.payload is not None else "")
    body = safe_text(body, client_options.token)
    if body:
        if json_output or not terminal:
            text = body
        else:
            text = render(json.loads(body, parse_int=str, parse_float=str), color=color)
        write(out, text if text.endswith("\n") else f"{text}\n")
    if criterion is None:
        return ExitCodes.SUCCESS
    verdict = evaluate(result.payload, criterion, tool.name)
    if verdict.message:
        write(err, safe_text(verdict.message, client_options.token) + "\n")
    return verdict.exit_code


def _invoke_and_handle(
    factory: Callable[[ClientOptions], Client],
    client_options: ClientOptions,
    tool: ManifestTool,
    args_payload: dict[str, Any],
    out: TextIO,
    err: TextIO,
    verbose: bool,
    json_output: bool,
    terminal: bool,
    color: bool,
    environment: Mapping[str, str],
    criterion: Criterion | None,
) -> int:
    called = _call_client(factory, client_options, tool.name, args_payload, err, verbose)
    if called is None:
        return ExitCodes.ERROR
    client, result = called
    return _emit_result(
        client, result, client_options, tool, out, err, verbose, json_output, terminal, color, environment, criterion
    )


def run(
    argv: Sequence[str],
    environment: Mapping[str, str],
    terminal: bool,
    out: TextIO,
    err: TextIO,
    client_factory: Callable[[ClientOptions], Client] | None = None,
) -> int:
    tokens = _usage_tokens(argv, environment)
    manifest = Manifest.bundled()
    selected_path = _selected_path(argv, manifest)
    root_parser = _get_root_parser(manifest, out, err, tokens, selected_path)

    try:
        namespace = root_parser.parse_args(list(argv))
    except _CliExit as exc:
        return exc.status

    builtin = getattr(namespace, "_builtin", None)
    global_options = _extract_global_options(namespace)
    client_options = global_options.to_client_options(environment)
    factory = client_factory or Client
    if builtin is not None:
        return _run_builtin(builtin, factory, client_options, out, err, terminal, global_options, environment)

    tool: ManifestTool | None = getattr(namespace, "_tool", None)
    if tool is None:
        active_parser = getattr(namespace, "_group_parser", root_parser)
        active_parser.print_usage(err)
        return ExitCodes.ERROR

    criterion: Criterion | None = None
    fail_value = getattr(namespace, "fail_on", None)
    if fail_value is not None:
        try:
            criterion = parse_fail_on(tool.name, fail_value)
        except ValueError as exc:
            _emit_error(err, str(exc), client_options.token)
            return ExitCodes.ERROR
    try:
        args_payload = _extract_tool_args(namespace, tool, root_parser, err, criterion)
    except _CliExit as exc:
        return exc.status
    if args_payload is None:
        return ExitCodes.ERROR

    try:
        return _invoke_and_handle(
            factory,
            client_options,
            tool,
            args_payload,
            out,
            err,
            global_options.verbose,
            global_options.json,
            terminal,
            global_options.color_output(terminal, environment),
            environment,
            criterion,
        )
    except Exception as exc:
        _emit_unexpected_error(err, exc, client_options.token, global_options.verbose)
        return ExitCodes.ERROR


def main(argv: Sequence[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    return run(args, os.environ, bool(sys.stdout.isatty()), sys.stdout, sys.stderr)


def _catalog_listing(catalog: dict[str, Any]) -> dict[str, object]:
    tools = cast(list[dict[str, Any]], catalog["tools"])
    rows: list[dict[str, object]] = []
    manifest = Manifest.bundled()
    for tool in tools:
        name = cast(str, tool.get("name", ""))
        known = manifest.by_name(name)
        action = cast(bool, tool.get("action", False))
        status = (
            "panel disabled"
            if not cast(bool, tool.get("panelEnabled", True))
            else "read-only"
            if action and cast(bool, tool.get("panelReadOnly", False))
            else "action"
            if action
            else "ready"
        )
        rows.append(
            {
                "command": known.command if known is not None else "-",
                "tool": name,
                "panel": tool.get("panel"),
                "arguments": ", ".join(cast(list[str], tool.get("arguments", []))) or "-",
                "status": status,
            }
        )
    return {
        "endpoint": catalog.get("endpoint"),
        "serverVersion": catalog.get("serverVersion"),
        "enabled": catalog.get("enabled"),
        "maxResults": catalog.get("maxResults"),
        "tools": rows,
    }


def _run_builtin(
    builtin: str,
    factory: Callable[[ClientOptions], Client],
    client_options: ClientOptions,
    out: TextIO,
    err: TextIO,
    terminal: bool,
    options: GlobalOptions,
    environment: Mapping[str, str],
) -> int:
    client: Client | None = None
    try:
        client = factory(client_options)
        if builtin == "tools":
            return _run_tools(client, out, terminal, options, environment)
        return _run_mcp(client, builtin.partition(":")[2], out, err, client_options, terminal, options, environment)
    except ClientError as exc:
        if builtin in {"mcp:enable", "mcp:disable"} and getattr(exc, "status", None) == 403:
            try:
                result = ToolResult("mcp_toggle", 403, exc.body, exc.payload)
                outcome = confirm_answered(client, result) if client is not None else None
                if outcome is not None and outcome.kind is OutcomeKind.REFUSED_BY_POLICY:
                    _emit_error(err, outcome.message + " (panel 'mcp-server')", client_options.token)
                    return ExitCodes.REFUSED
            except ClientError as confirmation_error:
                exc = confirmation_error
        _emit_client_error(err, exc, client_options.token, options.verbose)
        return ExitCodes.ERROR
    except Exception as exc:
        _emit_unexpected_error(err, exc, client_options.token, options.verbose)
        return ExitCodes.ERROR


def _run_tools(
    client: Client,
    out: TextIO,
    terminal: bool,
    options: GlobalOptions,
    environment: Mapping[str, str],
) -> int:
    payload = client.catalog()
    data: object = payload if options.json_output(terminal) else _catalog_listing(payload)
    text = (
        json.dumps(data, ensure_ascii=False, indent=2)
        if options.json_output(terminal)
        else render(data, color=options.color_output(terminal, environment))
    )
    write(out, text + "\n")
    return ExitCodes.SUCCESS


def _run_mcp(
    client: Client,
    action: str,
    out: TextIO,
    err: TextIO,
    client_options: ClientOptions,
    terminal: bool,
    options: GlobalOptions,
    environment: Mapping[str, str],
) -> int:
    payload = (
        client.get("/mcp-server")
        if action == "status"
        else client.post("/mcp-server/toggle", json.dumps({"enabled": action == "enable"}))
    )
    if not isinstance(payload, dict):
        _emit_error(err, "The target did not return a valid sharpit MCP server status report.", client_options.token)
        return ExitCodes.ERROR
    status = cast(dict[str, Any], payload)
    if (
        status.get("serverName") != "sharpit"
        or status.get("transport") != "http"
        or not isinstance(status.get("enabled"), bool)
        or not isinstance(status.get("tools"), list)
    ):
        _emit_error(err, "The target did not return a valid sharpit MCP server status report.", client_options.token)
        return ExitCodes.ERROR
    text = (
        json.dumps(status, ensure_ascii=False, indent=2)
        if options.json_output(terminal)
        else render(cast(dict[str, object], status), color=options.color_output(terminal, environment))
    )
    write(out, text + "\n")
    return ExitCodes.SUCCESS
