from __future__ import annotations

from typing import get_args, get_type_hints

import sharpit
from sharpit.engine import tools
from sharpit.engine.context import SharpitContext
from sharpit.engine.tools import CallContext, Tool, Via
from sharpit.fastapi.adapter import SharpitHandle


def _resolved_hints(function):
    try:
        return get_type_hints(function)
    except NameError:
        return {}


def test_install_return_type_resolves_at_runtime() -> None:
    hints = _resolved_hints(sharpit.install)

    assert hints.get("return") is SharpitHandle


def test_tool_call_types_resolve_at_runtime() -> None:
    hints = _resolved_hints(tools.call_tool)

    assert hints.get("call") is CallContext
    assert get_args(get_args(hints["tools"])[0])[0] is Tool


def test_tool_gate_context_and_via_types_resolve_at_runtime() -> None:
    hints = _resolved_hints(tools.tool_gate)

    assert hints.get("ctx") is SharpitContext
    assert hints.get("via") is Via
