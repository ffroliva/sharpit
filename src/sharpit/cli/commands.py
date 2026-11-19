"""Command tree and CLI dispatch for sharpit (BootUI's CommandTree and BootUiCli)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any, NoReturn, TextIO

from sharpit import __version__
from sharpit.cli.client import Client, ClientError, ToolResult, redact
from sharpit.cli.exit_codes import ExitCodes
from sharpit.cli.manifest import Manifest, ManifestTool
from sharpit.cli.options import ClientOptions, GlobalOptions, normalize_token, positive_seconds
from sharpit.cli.outcomes import OutcomeKind, confirm_answered

__all__ = ["main", "run"]

_ACTION_TAG = "[action - needs approval]"
_KNOWN_OPTIONS = frozenset(
    {
        "--url",
        "--api-path",
        "--token",
        "--timeout",
        "--json",
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
            target.write(message)
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


def _create_globals_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument(
        "--url",
        default=argparse.SUPPRESS,
        metavar="<text>",
        help="The application's base URL (SHARPIT_URL; default: http://localhost:8000)",
    )
    parser.add_argument(
        "--api-path",
        default=argparse.SUPPRESS,
        metavar="<text>",
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

    if tool.takes_query:
        leaf_parser.add_argument("-q", "--query", default=None, metavar="<text>", help="Filter results")
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
        and (index == 0 or argv[index - 1] not in {"--url", "--api-path", "--token", "--timeout"})
    )
    known_paths = {path for path, _ in manifest.command_specs}
    path = next(
        (candidates[:length] for length in range(len(candidates), 0, -1) if candidates[:length] in known_paths),
        None,
    )
    if path is None and candidates and "--help" not in argv and "-h" not in argv:
        return candidates[:1]
    return path


def _emit_error(err: TextIO, message: str, token: str | None, verbose: bool) -> None:  # noqa: ARG001
    message = redact(message, token)
    err.write(message)
    if not message.endswith("\n"):
        err.write("\n")
    if hasattr(err, "flush"):
        err.flush()


def _emit_client_error(err: TextIO, error: ClientError, token: str | None, verbose: bool) -> None:
    _emit_error(err, str(error), token, verbose)
    if verbose and error.__cause__ is not None:
        import traceback

        err.write(redact("".join(traceback.format_exception(error)), token))


def _emit_unexpected_error(err: TextIO, error: Exception, token: str | None, verbose: bool) -> None:
    if verbose:
        import traceback

        message = "".join(traceback.format_exception(error))
    else:
        message = " ".join(str(error).splitlines())
    _emit_error(err, message, token, verbose)


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


def _extract_tool_args(
    namespace: argparse.Namespace,
    tool: ManifestTool,
    root_parser: SharpitParser,
    err: TextIO,
) -> dict[str, Any] | None:
    args_payload: dict[str, Any] = {}
    leaf = getattr(namespace, "_leaf_parser", root_parser)

    if tool.takes_id:
        flag_id = getattr(namespace, "flag_id", None)
        pos_id = getattr(namespace, "pos_id", None)
        id_val = flag_id if flag_id is not None else pos_id
        if id_val is not None:
            args_payload["id"] = id_val
        elif "id" in tool.required or tool.schema in ("ID", "RULE_VIOLATIONS"):
            leaf.print_usage(err)
            err.write(f"{leaf.prog}: error: the following arguments are required: <id>\n")
            return None

    if tool.takes_scan_id:
        scan_id_val = getattr(namespace, "scan_id", None)
        if scan_id_val is not None:
            args_payload["scanId"] = scan_id_val
        elif "scanId" in tool.required or tool.schema == "RULE_VIOLATIONS":
            leaf.print_usage(err)
            err.write(f"{leaf.prog}: error: the following arguments are required: --scan-id\n")
            return None

    if tool.takes_offset and (offset := getattr(namespace, "offset", None)) is not None:
        args_payload["offset"] = offset
    if tool.takes_limit and (limit := getattr(namespace, "limit", None)) is not None:
        args_payload["limit"] = limit
    if tool.takes_query and (query := getattr(namespace, "query", None)) is not None:
        args_payload["query"] = query

    return args_payload


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
        _emit_error(err, "Client returned an invalid tool result", client_options.token, verbose)
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
) -> int:
    if 200 <= result.status < 300:
        body = result.raw_body or (json.dumps(result.payload) if result.payload is not None else "")
        if body:
            out.write(body if body.endswith("\n") else f"{body}\n")
        return ExitCodes.SUCCESS

    try:
        outcome = confirm_answered(client, result)
    except ClientError as exc:
        _emit_client_error(err, exc, client_options.token, verbose)
        return ExitCodes.ERROR

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
    _emit_error(err, message, client_options.token, verbose)
    return outcome.exit_code


def _invoke_and_handle(
    factory: Callable[[ClientOptions], Client],
    client_options: ClientOptions,
    tool: ManifestTool,
    args_payload: dict[str, Any],
    out: TextIO,
    err: TextIO,
    verbose: bool,
) -> int:
    called = _call_client(factory, client_options, tool.name, args_payload, err, verbose)
    if called is None:
        return ExitCodes.ERROR
    client, result = called
    return _emit_result(client, result, client_options, tool, out, err, verbose)


def run(
    argv: Sequence[str],
    environment: Mapping[str, str],
    terminal: bool,  # noqa: ARG001
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

    tool: ManifestTool | None = getattr(namespace, "_tool", None)
    if tool is None:
        active_parser = getattr(namespace, "_group_parser", root_parser)
        active_parser.print_usage(err)
        return ExitCodes.ERROR

    global_options = _extract_global_options(namespace)
    client_options = global_options.to_client_options(environment)
    try:
        args_payload = _extract_tool_args(namespace, tool, root_parser, err)
    except _CliExit as exc:
        return exc.status
    if args_payload is None:
        return ExitCodes.ERROR

    factory = client_factory or Client
    try:
        return _invoke_and_handle(factory, client_options, tool, args_payload, out, err, global_options.verbose)
    except Exception as exc:
        _emit_unexpected_error(err, exc, client_options.token, global_options.verbose)
        return ExitCodes.ERROR


def main(argv: Sequence[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    terminal = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False
    return run(args, os.environ, terminal, sys.stdout, sys.stderr)
