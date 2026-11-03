"""Tests for the application import graph and cycle detection (spec §5.5)."""

from __future__ import annotations

from pathlib import Path

from sharpit.engine import appsource
from sharpit.engine.collectors.architecture.graph import build_graph


def _write(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_cycle_detected_with_members(tmp_path: Path) -> None:
    pkg = tmp_path / "cycl_app"
    _write(pkg / "__init__.py")
    _write(pkg / "a.py", "import cycl_app.b\n")
    _write(pkg / "b.py", "import cycl_app.a\n")

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    cycles = graph.find_cycles()

    assert len(cycles) == 1
    assert set(cycles[0].members) == {"cycl_app.a", "cycl_app.b"}


def test_relative_imports_resolved(tmp_path: Path) -> None:
    pkg = tmp_path / "rel_app"
    _write(pkg / "__init__.py")
    _write(pkg / "common.py", "VAL = 1\n")
    _write(pkg / "sub" / "__init__.py")
    _write(pkg / "sub" / "b.py", "B = 2\n")
    _write(
        pkg / "sub" / "a.py",
        "from . import b\nfrom ..common import VAL\n",
    )

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    targets = [e.target for e in graph.edges.get("rel_app.sub.a", [])]

    assert "rel_app.sub.b" in targets
    assert "rel_app.common" in targets


def test_type_checking_imports_excluded(tmp_path: Path) -> None:
    pkg = tmp_path / "tc_app"
    _write(pkg / "__init__.py")
    _write(pkg / "runtime.py", "R = 1\n")
    _write(pkg / "types_only.py", "T = 2\n")
    _write(
        pkg / "consumer.py",
        "import tc_app.runtime\nfrom typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import tc_app.types_only\n",
    )

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    targets = [e.target for e in graph.edges.get("tc_app.consumer", [])]

    assert targets == ["tc_app.runtime"]


def test_conditional_import_is_an_edge(tmp_path: Path) -> None:
    pkg = tmp_path / "cond_app"
    _write(pkg / "__init__.py")
    _write(pkg / "target.py", "T = 1\n")
    _write(
        pkg / "consumer.py",
        "import sys\nif sys.platform == 'win32':\n    import cond_app.target\n",
    )

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    targets = [e.target for e in graph.edges.get("cond_app.consumer", [])]

    assert "cond_app.target" in targets


def test_external_imports_ignored(tmp_path: Path) -> None:
    pkg = tmp_path / "ext_app"
    _write(pkg / "__init__.py")
    _write(pkg / "internal.py", "I = 1\n")
    _write(
        pkg / "consumer.py",
        "import os\nimport sys\nimport fastapi\nimport ext_app.internal\n",
    )

    index = appsource.build_index(pkg, thread=False)
    graph = build_graph(index)
    targets = [e.target for e in graph.edges.get("ext_app.consumer", [])]

    assert targets == ["ext_app.internal"]


def test_deep_import_chain_does_not_crash() -> None:
    # an import chain deeper than the interpreter's recursion limit (bound: 2,000 files), closed into one cycle
    from sharpit.engine.collectors.architecture.graph import ImportEdge, ImportGraph  # noqa: PLC0415

    names = [f"deep_app.m{i:04d}" for i in range(3000)]
    graph = ImportGraph()
    graph.nodes.update(names)
    for i, name in enumerate(names):
        graph.edges[name] = [ImportEdge(name, names[(i + 1) % len(names)], 1, Path("m.py"))]

    try:
        cycles = graph.find_cycles()
    except RecursionError:
        cycles = []

    assert [len(c.members) for c in cycles] == [3000]
