"""``mysql: bool`` is gone (design section 10, step 3): a ``Dialect`` says how text is read, and no default chooses one.

``mysql`` stays where it is the collector's domain or a server's name: none of those chooses how text is read.
"""

from __future__ import annotations

import ast
import json
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

import sharpit
from sharpit.engine import sqla, tools
from sharpit.engine.activation import ActivationStatus
from sharpit.engine.capture.activity import request_profile
from sharpit.engine.capture.exchanges import HttpExchangeBuffer, exchange_row
from sharpit.engine.capture.sqltrace import ENTRY_KEYS, SqlTraceRecorder
from sharpit.engine.context import SharpitContext
from sharpit.engine.spi import AppInfo, ProviderInfo, RouteInfo
from sharpit.engine.sqltext import Dialect, lexer
from sharpit.settings import load_settings

SRC = Path(sharpit.__file__).resolve().parent
FLAG = "mysql"
GONE = frozenset({"MYSQL_DIALECTS", "is_mysql", "_span_is_mysql"})
ALLOWED = frozenset(
    {
        ("engine/collectors/database_advisor/catalog.py", "dict key"),  # the advisor's vendor table
        ("engine/collectors/postgresql/service.py", "dict key"),  # a label per server name
        ("engine/panels04/__init__.py", "dict key"),  # the panel
        ("engine/sqla/inspect.py", "dict key"),  # a query per engine name
        ("engine/sqltext/dialect.py", "dict key"),  # the one table of names
    }
)


def _dict_keys(node: ast.AST) -> list[ast.Constant]:
    """The ``"mysql"`` of ``{"mysql": ...}`` and of ``row["mysql"]``."""
    keys = node.keys if isinstance(node, ast.Dict) else [node.slice] if isinstance(node, ast.Subscript) else []
    return [key for key in keys if isinstance(key, ast.Constant) and key.value == FLAG]


def _names(node: ast.AST) -> list[tuple[str, str]]:
    """The kind and name each node holds. A string is data, unless a table of them exports the name."""
    holds: dict[type[ast.AST], tuple[str, str]] = {
        ast.arg: ("parameter", "arg"),
        ast.keyword: ("parameter", "arg"),
        ast.Attribute: ("attribute", "attr"),
        ast.Name: ("variable", "id"),
        ast.FunctionDef: ("name", "name"),
        ast.Constant: ("name", "value"),
    }
    if isinstance(node, ast.ImportFrom):
        return [("name", alias.name) for alias in node.names]
    kind, field = holds.get(type(node), ("", ""))
    return [(kind, getattr(node, field))] if kind else []


def _named(kind: str, name: object, node: ast.AST) -> bool:
    if name in GONE:
        return True
    if name != FLAG or kind == "name":
        return False
    return kind != "variable" or isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)


def _nodes(tree: ast.AST) -> Iterator[tuple[str, str, int]]:
    """Each place ``tree`` names the flag: its kind, the name, the line."""
    for node in ast.walk(tree):
        for kind, name in _names(node):
            if _named(kind, name, node):
                yield kind, str(name), getattr(node, "lineno", 0)
        yield from (("dict key", FLAG, key.lineno) for key in _dict_keys(node))


def flag_sites(root: Path) -> list[str]:
    sites: list[str] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        for kind, name, line in _nodes(ast.parse(path.read_text(encoding="utf-8"))):
            if (rel, kind) not in ALLOWED:
                sites.append(f"{rel}:{line} {kind} {name}")
    return sites


def _reads_with_a_default(tree: ast.AST) -> Iterator[int]:
    for node in ast.walk(tree):
        match node:
            case ast.Call(func=ast.Attribute(attr="get"), args=[ast.Constant(value="mysql" | "dialect"), *_]):
                yield node.lineno
            case _:
                pass


def default_reads(root: Path) -> list[str]:
    return [
        f"{path.relative_to(root).as_posix()}:{line}"
        for path in sorted(root.rglob("*.py"))
        for line in _reads_with_a_default(ast.parse(path.read_text(encoding="utf-8")))
    ]


def test_no_mysql_flag_is_left() -> None:
    assert flag_sites(SRC) == []


def test_a_planted_mysql_flag_fails(tmp_path: Path) -> None:
    (tmp_path / "planted.py").write_text("def f(mysql: bool = False) -> bool:\n    return mysql\n", encoding="utf-8")

    assert flag_sites(tmp_path) == ["planted.py:1 parameter mysql"]


def test_no_row_reads_a_dialect_with_a_default() -> None:
    assert default_reads(SRC) == []


def test_a_planted_default_read_fails(tmp_path: Path) -> None:
    (tmp_path / "planted.py").write_text('def f(row):\n    return row.get("mysql", False)\n', encoding="utf-8")

    assert default_reads(tmp_path) == ["planted.py:2"]


def dialect_members_outside_readings(source: str) -> list[str]:
    tree = ast.parse(source)
    allowed = {
        id(inner)
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "readings"
        for inner in ast.walk(node)
    }
    return [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "Dialect"
        and id(node) not in allowed
    ]


def test_the_lexer_never_names_a_dialect() -> None:
    assert dialect_members_outside_readings(Path(lexer.__file__).read_text(encoding="utf-8")) == []


def test_a_planted_dialect_member_in_the_lexer_fails(tmp_path: Path) -> None:
    copy = tmp_path / "lexer.py"
    shutil.copy(lexer.__file__, copy)
    with copy.open("a", encoding="utf-8") as planted:
        planted.write("\n\nPLANTED = Dialect.SQLITE\n")

    assert "SQLITE" in dialect_members_outside_readings(copy.read_text(encoding="utf-8"))


class _Introspector:
    def app_info(self) -> AppInfo:
        return AppInfo("demo", "FastAPI", "0.115.0", None)

    def routes(self) -> list[RouteInfo]:
        return []

    def providers(self) -> list[ProviderInfo]:
        return []


REQUEST = "r1"


def _ctx() -> SharpitContext:
    ctx = SharpitContext(
        load_settings({"config_scan": False}, {}),
        ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ()),
        _Introspector(),
    )
    recorder = ctx.capture.sql_trace = SqlTraceRecorder(ctx.masker)
    ctx.capture.exchanges = HttpExchangeBuffer(10)
    ctx.capture.exchanges.add(
        exchange_row(
            ctx.masker,
            request_id=REQUEST,
            started_epoch_ns=1,
            method="GET",
            path="/x",
            query_string=b"",
            status=200,
            duration_ms=1,
            size=0,
            client=None,
            user=None,
            request_headers=[],
            response_headers=[],
            finished_epoch_ns=2,
        )
    )
    recorder.record(
        "select 1", duration_ns=1, thread="t", connection_id=None, request_id=REQUEST, dialect=Dialect.UNSUPPORTED
    )
    return ctx


def _report(ctx: SharpitContext) -> list[dict[str, Any]]:
    assert ctx.capture.sql_trace is not None
    return ctx.capture.sql_trace.report([])["entries"]


def _profile(ctx: SharpitContext) -> list[dict[str, Any]]:
    return request_profile(ctx, REQUEST)["sql"]


def _mcp(ctx: SharpitContext) -> list[dict[str, Any]]:
    return tools._sql_traces_view(ctx, None, 10)["entries"]  # noqa: SLF001


SURFACES: dict[str, Callable[[SharpitContext], list[dict[str, Any]]]] = {
    "report": _report,
    "request_profile": _profile,
    "mcp": _mcp,
}


@pytest.fixture(autouse=True)
def _sqlalchemy_imported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sqla, "unavailable_reason", lambda: None)


@pytest.mark.parametrize("surface", SURFACES)
def test_no_internal_key_reaches_an_entry(surface: str) -> None:
    entries = SURFACES[surface](_ctx())

    assert [sorted(entry) for entry in entries] == [sorted(ENTRY_KEYS)]
    assert json.dumps(entries)


@pytest.mark.parametrize("surface", SURFACES)
def test_a_planted_row_key_reaches_an_entry(surface: str) -> None:
    # the check above needs teeth: a key the row gains and ``entry_dto`` does not pop shows on all three
    ctx = _ctx()
    assert ctx.capture.sql_trace is not None
    ctx.capture.sql_trace.rows()[0]["dialect"] = Dialect.UNSUPPORTED

    entries = SURFACES[surface](ctx)

    assert sorted(entries[0]) == sorted([*ENTRY_KEYS, "dialect"])
    with pytest.raises(TypeError):
        json.dumps(entries)
