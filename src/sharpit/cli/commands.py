"""Command tree and CLI dispatch for sharpit (BootUI's CommandTree and BootUiCli)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any, NoReturn, TextIO

from sharpit import __version__
from sharpit.cli.client import Client, ClientError, ToolResult
from sharpit.cli.manifest import Manifest, ManifestTool
from sharpit.cli.options import ClientOptions, GlobalOptions, positive_seconds

__all__ = ["main", "run"]

_ACTION_TAG = "[action - needs approval]"


class _CliExit(Exception):
    def __init__(self, status: int) -> None:
        self.status = status
        super().__init__(status)


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
        self._out = out
        self._err = err

    def _print_message(self, message: str, file: Any = None) -> None:
        target = self._out if file is None or file is sys.stdout or file is self._out else self._err or file
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
        if "invalid choice:" in message:
            message = "invalid command or option"
        self.exit(1, f"{self.prog}: error: {message}\n")


def _create_globals_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--url",
        default=argparse.SUPPRESS,
        help="The application's base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--api-path",
        default=argparse.SUPPRESS,
        help="The sharpit API path (default: /sharpit/api)",
    )
    parser.add_argument(
        "--token",
        default=argparse.SUPPRESS,
        help="Authentication bearer token",
    )
    parser.add_argument(
        "--timeout",
        type=positive_seconds,
        default=argparse.SUPPRESS,
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
    return parser


def _configure_leaf_arguments(leaf_parser: SharpitParser, tool: ManifestTool) -> None:
    desc = f"{_ACTION_TAG} {tool.description}" if tool.action else tool.description
    leaf_parser.description = desc
    leaf_parser.formatter_class = argparse.RawDescriptionHelpFormatter
    leaf_parser.help = tool.summary
    leaf_parser.epilog = f"Example: {tool.example}\nMCP tool: {tool.name}"
    leaf_parser.set_defaults(_tool=tool, _leaf_parser=leaf_parser)

    if tool.takes_query:
        leaf_parser.add_argument("-q", "--query", default=None, help="Filter results")
    if tool.takes_limit or tool.schema == "QUERY":
        help_text = "Return at most this many results" if tool.takes_limit else argparse.SUPPRESS
        leaf_parser.add_argument("-n", "--limit", type=int, default=None, help=help_text)
    if tool.takes_id:
        leaf_parser.add_argument("pos_id", nargs="?", default=None, metavar="<id>", help="Identifier")
        leaf_parser.add_argument("--id", dest="flag_id", default=None, help="Identifier")
    if tool.takes_scan_id:
        leaf_parser.add_argument("--scan-id", dest="scan_id", default=None, help="Scan ID")
    if tool.takes_offset:
        leaf_parser.add_argument("--offset", type=int, default=None, help="Offset")


def _ensure_group_parser(
    parsers: dict[tuple[str, ...], SharpitParser],
    subparsers: dict[tuple[str, ...], Any],
    parent_prefix: tuple[str, ...],
    word: str,
    out: TextIO,
    err: TextIO,
    globals_parser: argparse.ArgumentParser,
) -> SharpitParser:
    current_prefix = (*parent_prefix, word)
    if current_prefix in parsers:
        return parsers[current_prefix]
    parent_parser = parsers[parent_prefix]
    if parent_prefix not in subparsers:
        subparsers[parent_prefix] = parent_parser.add_subparsers(
            dest=f"_sub_{len(parent_prefix)}",
            parser_class=lambda **kw: SharpitParser(out=out, err=err, **kw),
        )
    sub = subparsers[parent_prefix]
    group_parser: SharpitParser = sub.add_parser(word, parents=[globals_parser], allow_abbrev=False)
    group_parser.set_defaults(_group_parser=group_parser)
    parsers[current_prefix] = group_parser
    return group_parser


_parser_cache: dict[int, SharpitParser] = {}


def _build_root_parser(manifest: Manifest, out: TextIO, err: TextIO) -> SharpitParser:
    cached = _parser_cache.get(id(manifest))
    if cached is not None:
        pending = [cached]
        while pending:
            parser = pending.pop()
            parser._out, parser._err = out, err
            pending.extend(
                child
                for action in parser._actions
                if isinstance(action, argparse._SubParsersAction)
                for child in action.choices.values()
            )
        return cached
    globals_parser = _create_globals_parser()
    root = SharpitParser(
        prog="sharpit",
        description="Ask a running sharpit application a question.",
        parents=[globals_parser],
        out=out,
        err=err,
    )
    root.add_argument("--version", action="version", version=f"sharpit {__version__}")
    root.add_argument("-V", action="version", version=f"sharpit {__version__}")

    parsers_by_prefix: dict[tuple[str, ...], SharpitParser] = {(): root}
    subparsers_by_prefix: dict[tuple[str, ...], Any] = {}

    for tool in manifest.tools:
        path = tool.path
        for depth in range(len(path) - 1):
            _ensure_group_parser(
                parsers_by_prefix, subparsers_by_prefix, path[:depth], path[depth], out, err, globals_parser
            )

        parent_prefix = path[:-1]
        leaf_word = path[-1]
        parent_parser = parsers_by_prefix[parent_prefix]
        if parent_prefix not in subparsers_by_prefix:
            subparsers_by_prefix[parent_prefix] = parent_parser.add_subparsers(
                dest=f"_sub_{len(parent_prefix)}",
                parser_class=lambda **kw: SharpitParser(out=out, err=err, **kw),
            )
        leaf_sub = subparsers_by_prefix[parent_prefix]
        leaf_parser: SharpitParser = leaf_sub.add_parser(
            leaf_word, parents=[globals_parser], allow_abbrev=False, help=tool.summary
        )
        _configure_leaf_arguments(leaf_parser, tool)

    _parser_cache[id(manifest)] = root
    return root


def _emit_error(err: TextIO, message: str, token: str | None, verbose: bool) -> None:  # noqa: ARG001
    if token:
        message = message.replace(f"Bearer {token}", "Bearer [redacted]")
        message = message.replace(token, "[redacted]")
    err.write(message)
    if not message.endswith("\n"):
        err.write("\n")
    if hasattr(err, "flush"):
        err.flush()


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
        id_val = getattr(namespace, "flag_id", None) or getattr(namespace, "pos_id", None)
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


def _invoke_client(
    factory: Callable[[ClientOptions], Client],
    client_options: ClientOptions,
    tool_name: str,
    args_payload: dict[str, Any],
    err: TextIO,
    verbose: bool,
) -> Any | None:
    try:
        client = factory(client_options)
    except ClientError as exc:
        _emit_error(err, str(exc), client_options.token, verbose)
        return None
    except Exception:
        if verbose:
            import traceback

            err.write(traceback.format_exc())
        raise

    try:
        return client.invoke(tool_name, args_payload)
    except ClientError as exc:
        _emit_error(err, str(exc), client_options.token, verbose)
        return None
    except Exception:
        if verbose:
            import traceback

            err.write(traceback.format_exc())
        raise


def _handle_result(
    result: ToolResult,
    client_options: ClientOptions,
    out: TextIO,
    err: TextIO,
    verbose: bool,
) -> int:
    if not isinstance(result, ToolResult):
        _emit_error(err, "Client returned an invalid tool result", client_options.token, verbose)
        return 1
    status = result.status
    raw_body = result.raw_body
    payload = result.payload

    if 200 <= status < 300:
        if raw_body:
            out.write(raw_body)
            if not raw_body.endswith("\n"):
                out.write("\n")
        elif payload is not None:
            out.write(json.dumps(payload))
            out.write("\n")
        return 0

    err_msg = raw_body or (json.dumps(payload) if payload else f"sharpit answered HTTP {status}")
    _emit_error(err, err_msg, client_options.token, verbose)
    if status == 403 and isinstance(payload, dict) and payload.get("error") == "sharpit panel access denied":
        return 2
    return 1


def run(
    argv: Sequence[str],
    environment: Mapping[str, str],
    terminal: bool,  # noqa: ARG001
    out: TextIO,
    err: TextIO,
    client_factory: Callable[[ClientOptions], Client] | None = None,
) -> int:
    manifest = Manifest.bundled()
    root_parser = _build_root_parser(manifest, out, err)

    try:
        namespace = root_parser.parse_args(list(argv))
    except _CliExit as exc:
        return exc.status

    tool: ManifestTool | None = getattr(namespace, "_tool", None)
    if tool is None:
        active_parser = getattr(namespace, "_group_parser", root_parser)
        active_parser.print_usage(err)
        return 1

    global_options = _extract_global_options(namespace)
    client_options = global_options.to_client_options(environment)
    args_payload = _extract_tool_args(namespace, tool, root_parser, err)
    if args_payload is None:
        return 1

    factory = client_factory or Client
    result = _invoke_client(factory, client_options, tool.name, args_payload, err, global_options.verbose)
    if result is None:
        return 1

    return _handle_result(result, client_options, out, err, global_options.verbose)


def main(argv: Sequence[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    terminal = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False
    return run(args, os.environ, terminal, sys.stdout, sys.stderr)
