"""Command tree and CLI dispatch for sharpit (BootUI's CommandTree and BootUiCli)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, NoReturn, TextIO, cast

from sharpit import __version__
from sharpit.cli.arguments import build_tool_arguments
from sharpit.cli.client import (
    AUTHENTICATION_HINT,
    REDACTED,
    Client,
    ClientError,
    ToolResult,
    redact_json,
    redact_payload,
    safe_text,
)
from sharpit.cli.exit_codes import ExitCodes
from sharpit.cli.fail_on import EXCLUDED, Criterion, evaluate, supports_insufficient, supports_severity
from sharpit.cli.fail_on import parse as parse_fail_on
from sharpit.cli.manifest import Manifest, ManifestTool
from sharpit.cli.options import ClientOptions, GlobalOptions, normalize_token, positive_seconds
from sharpit.cli.outcomes import OutcomeKind, confirm_answered
from sharpit.cli.render import render, safe_controls, write, write_json

__all__ = ["main", "run"]

_ACTION_TAG = "[action - needs approval]"
_UNKNOWN_MCP_OUTCOME = (
    "The MCP action outcome is unknown: no valid sharpit MCP server status acknowledgement was received. "
    "The action was not retried."
)


class _CliExit(Exception):
    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(status)


class _Emission:
    def __init__(self, token: str | None, json_output: bool, terminal: bool, color: bool) -> None:
        self.token = token
        self.json_output = json_output
        self.terminal = terminal
        self.color = color


class _JsonNumber(str):
    pass


def _emit(out: TextIO, raw_body: str, payload: object, options: _Emission) -> None:
    if options.json_output or not options.terminal:
        text = redact_json(raw_body or (json.dumps(payload) if payload is not None else ""), options.token)
        if options.terminal:
            text = _escape_json_controls(text)
    else:
        text = render(redact_payload(payload, options.token), color=options.color)
    if text:
        (write_json if options.json_output or not options.terminal else write)(
            out, text if text.endswith("\n") else f"{text}\n"
        )
    if hasattr(out, "flush"):
        out.flush()


def _redact_usage_error(message: str, tokens: Sequence[str] = ()) -> str:
    msg = message
    for token in tokens:
        if token:
            msg = msg.replace(token, REDACTED)
    return msg


def _escape_json_controls(text: str) -> str:
    return "".join(
        f"\\u{ord(char):04x}" if char not in "\n\t" and (ord(char) < 32 or 0x7F <= ord(char) <= 0x9F) else char
        for char in text
    )


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
            write(target, safe_controls(message))
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

    if tool.name in EXCLUDED or supports_severity(tool.name) or supports_insufficient(tool.name):
        leaf_parser.add_argument(
            "--fail-on", default=argparse.SUPPRESS, metavar="<severity>", help="Exit 3 at or above this severity"
        )

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
    # Root placement supports the conventional ``sharpit --fail-on high tool`` form;
    # built-in commands still reject it after parsing.
    root.add_argument("--fail-on", default=argparse.SUPPRESS, metavar="<severity>", help=argparse.SUPPRESS)
    all_parsers: list[SharpitParser] = [root]
    parsers_by_prefix: dict[tuple[str, ...], SharpitParser] = {(): root}
    subparsers_by_prefix: dict[tuple[str, ...], Any] = {}

    for tool in _selected_tools(manifest, selected_path):
        _add_tool_parser(tool, globals_parser, parsers_by_prefix, subparsers_by_prefix, all_parsers)

    root_sub = _get_or_create_subparsers((), parsers_by_prefix, subparsers_by_prefix)
    tools_parser: SharpitParser = root_sub.add_parser(
        "tools",
        parents=[globals_parser],
        allow_abbrev=False,
        help="List tools advertised by the running application.",
        description="List the tools this application exposes, and whether its panels allow each one.",
    )
    tools_parser.set_defaults(_builtin="tools")
    all_parsers.append(tools_parser)
    mcp_parser: SharpitParser = root_sub.add_parser(
        "mcp",
        parents=[globals_parser],
        allow_abbrev=False,
        help="Inspect and toggle the application's MCP server (status, enable, disable).",
        description="Inspect and toggle the application's MCP server.",
    )
    mcp_parser.set_defaults(_group_parser=mcp_parser)
    all_parsers.append(mcp_parser)
    mcp_sub = mcp_parser.add_subparsers(dest="mcp_action", metavar="<command>")
    for action, description in (
        ("status", "Show the MCP server state and advertised tools."),
        ("enable", "Turn the MCP server on for this running application."),
        ("disable", "Turn the MCP server off for this running application."),
    ):
        leaf: SharpitParser = mcp_sub.add_parser(
            action,
            parents=[cast(Any, globals_parser)],
            allow_abbrev=False,
            help=description,
            description=description,
        )
        leaf.set_defaults(_builtin=f"mcp:{action}")
        all_parsers.append(leaf)

    return root, all_parsers


def _selected_tools(manifest: Manifest, selected_path: tuple[str, ...] | None) -> Iterable[ManifestTool]:
    if selected_path is None:
        return (tool for _, tool in manifest.command_specs)
    if selected_path:
        return (tool for path, tool in manifest.command_specs if path[: len(selected_path)] == selected_path)
    return iter(())


def _get_or_create_subparsers(
    prefix: tuple[str, ...],
    parsers_by_prefix: dict[tuple[str, ...], SharpitParser],
    subparsers_by_prefix: dict[tuple[str, ...], Any],
) -> Any:
    if prefix not in subparsers_by_prefix:
        subparsers_by_prefix[prefix] = parsers_by_prefix[prefix].add_subparsers(
            dest="command" if not prefix else "subcommand",
            metavar="<command>" if not prefix else None,
        )
    return subparsers_by_prefix[prefix]


def _add_tool_parser(
    tool: ManifestTool,
    globals_parser: argparse.ArgumentParser,
    parsers_by_prefix: dict[tuple[str, ...], SharpitParser],
    subparsers_by_prefix: dict[tuple[str, ...], Any],
    all_parsers: list[SharpitParser],
) -> None:
    for depth in range(len(tool.path) - 1):
        prefix = tool.path[:depth]
        word = tool.path[depth]
        child_prefix = (*prefix, word)
        if child_prefix not in parsers_by_prefix:
            sub = _get_or_create_subparsers(prefix, parsers_by_prefix, subparsers_by_prefix)
            group: SharpitParser = sub.add_parser(word, parents=[globals_parser], allow_abbrev=False)
            group.set_defaults(_group_parser=group)
            parsers_by_prefix[child_prefix] = group
            all_parsers.append(group)

    leaf_sub = _get_or_create_subparsers(tool.path[:-1], parsers_by_prefix, subparsers_by_prefix)
    leaf_parser: SharpitParser = leaf_sub.add_parser(
        tool.path[-1], parents=[globals_parser], allow_abbrev=False, help=tool.summary
    )
    _configure_leaf_arguments(leaf_parser, tool)
    all_parsers.append(leaf_parser)


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
    for index, value in enumerate(argv):
        option, separator, attached = value.partition("=")
        if value.lower() == "--token" and index + 1 < len(argv):
            tokens.extend((argv[index + 1], normalize_token(argv[index + 1]) or ""))
        elif option.lower() == "--token" and separator:
            tokens.extend((attached, normalize_token(attached) or ""))
        elif _token_like_flag(option):
            if separator:
                tokens.append(attached)
            elif index + 1 < len(argv):
                tokens.append(argv[index + 1])
    return tuple(tokens)


def _token_like_flag(option: str) -> bool:
    candidate = option.lower()
    if any(part in candidate for part in ("token", "secret", "pass", "key", "bearer", "auth", "credential")):
        return True
    target = "--token"
    if abs(len(candidate) - len(target)) > 2:
        return False
    previous = list(range(len(candidate) + 1))
    for row, char in enumerate(target, 1):
        current = [row]
        for column, other in enumerate(candidate, 1):
            current.append(min(current[-1] + 1, previous[column] + 1, previous[column - 1] + (char != other)))
        previous = current
    return previous[-1] <= 2


def _selected_path(argv: Sequence[str], manifest: Manifest) -> tuple[str, ...] | None:
    candidates = tuple(
        value
        for index, value in enumerate(argv)
        if not value.startswith("-")
        and (index == 0 or argv[index - 1] not in {"--url", "--api-path", "--token", "--timeout", "--fail-on"})
    )
    known_paths = {path for path, _ in manifest.command_specs}
    if candidates and candidates[0] in {"tools", "mcp"}:
        return ()
    path = next(
        (candidates[:length] for length in range(len(candidates), 0, -1) if candidates[:length] in known_paths),
        None,
    )
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

        _emit_error(err, "".join(traceback.format_exception(error)), token)


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
            "The sharpit command-line endpoint is disabled on this application. "
            "Set SHARPIT_CLI_ENABLED=true to allow it."
        )
    elif outcome.kind is OutcomeKind.UNKNOWN_TOOL:
        message = outcome.message
    elif outcome.kind is OutcomeKind.UNAUTHENTICATED:
        message += ". " + AUTHENTICATION_HINT
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
    payload = result.payload
    if not json_output and terminal and body:
        payload = json.loads(body, parse_int=_JsonNumber, parse_float=_JsonNumber)
    _emit(out, body, payload, _Emission(client_options.token, json_output, terminal, color))
    if criterion is None:
        return ExitCodes.SUCCESS
    verdict = evaluate(result.payload, criterion, tool.name)
    if verdict.message:
        _emit_error(err, verdict.message, client_options.token)
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
    criterion: Criterion | None,
) -> int:
    called = _call_client(factory, client_options, tool.name, args_payload, err, verbose)
    if called is None:
        return ExitCodes.ERROR
    client, result = called
    return _emit_result(
        client, result, client_options, tool, out, err, verbose, json_output, terminal, color, criterion
    )


def _parse_command(parser: SharpitParser, argv: Sequence[str]) -> argparse.Namespace | int:
    try:
        return parser.parse_args(list(argv))
    except _CliExit as exc:
        return exc.status


def _usage_failure(parser: SharpitParser, message: str) -> int:
    try:
        parser.error(message)
    except _CliExit:
        return ExitCodes.ERROR


def _tool_criterion(
    tool: ManifestTool, value: str | None, parser: SharpitParser, err: TextIO, token: str | None
) -> Criterion | int | None:
    if value is None:
        return None
    try:
        return parse_fail_on(tool.name, value)
    except ValueError as exc:
        _emit_error(err, str(exc), token)
        return ExitCodes.ERROR


def _run_tool_command(
    namespace: argparse.Namespace,
    parser: SharpitParser,
    factory: Callable[[ClientOptions], Client],
    client_options: ClientOptions,
    global_options: GlobalOptions,
    terminal: bool,
    out: TextIO,
    err: TextIO,
    environment: Mapping[str, str],
) -> int:
    tool: ManifestTool | None = getattr(namespace, "_tool", None)
    if tool is None:
        if getattr(namespace, "fail_on", None) is not None:
            return _usage_failure(parser, "--fail-on requires a supported tool command")
        getattr(namespace, "_group_parser", parser).print_usage(err)
        return ExitCodes.ERROR

    criterion = _tool_criterion(tool, getattr(namespace, "fail_on", None), parser, err, client_options.token)
    if isinstance(criterion, int):
        return criterion
    try:
        args_payload = _extract_tool_args(namespace, tool, parser, err, criterion)
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
            criterion,
        )
    except BrokenPipeError:
        raise
    except Exception as exc:
        _emit_unexpected_error(err, exc, client_options.token, global_options.verbose)
        return ExitCodes.ERROR


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

    parsed = _parse_command(root_parser, argv)
    if isinstance(parsed, int):
        return parsed
    namespace = parsed

    builtin = getattr(namespace, "_builtin", None)
    global_options = _extract_global_options(namespace)
    client_options = global_options.to_client_options(environment)
    factory = client_factory or Client
    if builtin is not None:
        if getattr(namespace, "fail_on", None) is not None:
            return _usage_failure(root_parser, "--fail-on is only supported by tool commands")
        return _run_builtin(builtin, factory, client_options, out, err, terminal, global_options, environment)

    return _run_tool_command(
        namespace, root_parser, factory, client_options, global_options, terminal, out, err, environment
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    terminal = bool(sys.stdout.isatty())
    if not terminal:
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure is not None:
                reconfigure(encoding="utf-8")
    try:
        return run(args, os.environ, terminal, sys.stdout, sys.stderr)
    except BrokenPipeError:
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            try:
                os.dup2(devnull, sys.stdout.fileno())
            finally:
                os.close(devnull)
        except OSError:  # noqa: SIM105 - preserve the non-success result if stdout cannot be redirected.
            pass
        return ExitCodes.ERROR
    except KeyboardInterrupt:
        return 130


def _catalog_listing(catalog: dict[str, object]) -> dict[str, object]:
    raw_tools = catalog.get("tools", [])
    tools = cast(list[object], raw_tools) if isinstance(raw_tools, list) else []
    manifest = Manifest.bundled()
    rows = [_catalog_tool_row(item, manifest) for item in tools]
    return {
        "endpoint": catalog.get("endpoint"),
        "serverVersion": catalog.get("serverVersion"),
        "enabled": catalog.get("enabled"),
        "maxResults": catalog.get("maxResults"),
        "tools": rows,
    }


def _catalog_tool_row(item: object, manifest: Manifest) -> dict[str, object]:
    tool = cast(dict[str, object], item) if isinstance(item, dict) else {}
    raw_name = tool.get("name")
    name = raw_name if isinstance(raw_name, str) else ""
    known = manifest.by_name(name)
    raw_arguments = tool.get("arguments")
    arguments = (
        [value for value in cast(list[object], raw_arguments) if isinstance(value, str) and value]
        if isinstance(raw_arguments, list)
        else []
    )
    return {
        "command": known.command if known is not None else "-",
        "tool": name,
        "panel": tool.get("panel") if isinstance(tool.get("panel"), str) else "",
        "arguments": ", ".join(arguments) or "-",
        "status": _catalog_status(tool),
    }


def _catalog_status(tool: dict[str, object]) -> str:
    action = tool.get("action") is True
    if tool.get("panelEnabled") is False:
        return "panel disabled"
    if action and tool.get("panelReadOnly") is True:
        return "read-only"
    if action:
        return "action"
    return "ready"


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
        _emit_client_error(err, exc, client_options.token, options.verbose)
        return ExitCodes.ERROR
    except BrokenPipeError:
        raise
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
    response = client.catalog_result()
    payload: object = response.payload
    if not isinstance(payload, dict):
        raise ClientError("The target did not return a valid sharpit catalog.")
    catalog = cast(dict[str, object], payload)
    if options.json_output(terminal):
        displayed: object = cast(dict[str, object], payload)
    else:
        displayed = _catalog_listing(catalog)
    _emit(
        out,
        response.raw_body,
        displayed,
        _Emission(
            client.options.token, options.json_output(terminal), terminal, options.color_output(terminal, environment)
        ),
    )
    return ExitCodes.SUCCESS


def _valid_mcp_report(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    status = cast(dict[str, object], payload)
    tools = status.get("tools")
    if not isinstance(tools, list):
        return False
    for entry in cast(list[object], tools):
        tool = cast(dict[str, object], entry) if isinstance(entry, dict) else {}
        name = tool.get("name")
        if not isinstance(name, str) or not name.strip() or not isinstance(tool.get("action"), bool):
            return False
    return (
        status.get("serverName") == "sharpit"
        and status.get("transport") == "http"
        and isinstance(status.get("enabled"), bool)
    )


def _invalid_mcp_message(action: str) -> str:
    return (
        _UNKNOWN_MCP_OUTCOME
        if action != "status"
        else "The target did not return a valid sharpit MCP server status report."
    )


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
    response: ToolResult | None = None
    try:
        if action == "status":
            response = client.get_result("/mcp-server")
        else:
            response = client.post_result("/mcp-server/toggle", json.dumps({"enabled": action == "enable"}))
        payload = response.payload
    except ClientError as error:
        if action != "status" and error.request_sent:
            _emit_error(err, _UNKNOWN_MCP_OUTCOME, client_options.token)
            return ExitCodes.ERROR
        raise
    if not _valid_mcp_report(payload):
        _emit_error(err, _invalid_mcp_message(action), client_options.token)
        return ExitCodes.ERROR
    status = cast(dict[str, object], payload)
    _emit(
        out,
        response.raw_body,
        status,
        _Emission(
            client_options.token, options.json_output(terminal), terminal, options.color_output(terminal, environment)
        ),
    )
    return ExitCodes.SUCCESS
