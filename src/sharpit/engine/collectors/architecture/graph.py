"""AST import graph and cycle detection for application packages (spec §5.5)."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from sharpit.engine.appsource import ModuleInfo, SourceIndex


@dataclass(frozen=True)
class ImportEdge:
    source: str
    target: str
    line: int
    path: Path


@dataclass(frozen=True)
class Cycle:
    members: tuple[str, ...]
    edges: tuple[ImportEdge, ...] = ()


def _is_type_checking(node: ast.expr) -> bool:
    if isinstance(node, ast.Name) and node.id == "TYPE_CHECKING":
        return True
    return isinstance(node, ast.Attribute) and node.attr == "TYPE_CHECKING"


def _walk_ast(tree: ast.AST) -> Iterator[ast.AST]:
    """Walk AST nodes excluding the bodies of ``if TYPE_CHECKING:`` blocks."""
    stack = [tree]
    while stack:
        current = stack.pop()
        yield current
        if isinstance(current, ast.If) and _is_type_checking(current.test):
            stack.extend(reversed(current.orelse))
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(current))))


def _package_of(module_name: str, path: Path) -> str:
    return module_name if path.name == "__init__.py" else module_name.rpartition(".")[0]


def _resolve_relative(package: str, level: int, module: str | None) -> str | None:
    parts = package.split(".") if package else []
    keep = len(parts) - level + 1
    if level and keep <= 0:
        return None
    base = parts[:keep] if level else []
    return ".".join([*base, module] if module else base)


@dataclass
class ImportGraph:
    nodes: set[str] = field(default_factory=set[str])
    edges: dict[str, list[ImportEdge]] = field(default_factory=dict[str, list[ImportEdge]])

    def find_cycles(self) -> list[Cycle]:
        """Tarjan strongly connected components of size >= 2 over module edges."""
        return _tarjan_cycles(self.nodes, self.edges)

    def find_package_cycles(self) -> list[Cycle]:
        """Tarjan strongly connected components of size >= 2 over package-level projections."""
        pkg_nodes: set[str] = set()
        pkg_edges: dict[str, list[ImportEdge]] = {}
        for source, edges in self.edges.items():
            src_pkg = source.rpartition(".")[0] if "." in source else source
            pkg_nodes.add(src_pkg)
            for edge in edges:
                tgt_pkg = edge.target.rpartition(".")[0] if "." in edge.target else edge.target
                if src_pkg != tgt_pkg:
                    pkg_nodes.add(tgt_pkg)
                    pkg_edges.setdefault(src_pkg, []).append(ImportEdge(src_pkg, tgt_pkg, edge.line, edge.path))
        return _tarjan_cycles(pkg_nodes, pkg_edges)


def _tarjan_cycles(nodes: set[str], edges: dict[str, list[ImportEdge]]) -> list[Cycle]:
    index_counter = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    cycles: list[Cycle] = []

    sorted_nodes = sorted(nodes)

    def strongconnect(v: str) -> None:
        nonlocal index_counter
        indices[v] = index_counter
        lowlinks[v] = index_counter
        index_counter += 1
        stack.append(v)
        on_stack.add(v)

        for edge in edges.get(v, []):
            w = edge.target
            if w not in nodes:
                continue
            if w not in indices:
                strongconnect(w)
                lowlinks[v] = min(lowlinks[v], lowlinks[w])
            elif w in on_stack:
                lowlinks[v] = min(lowlinks[v], indices[w])

        if lowlinks[v] == indices[v]:
            scc: list[str] = []
            while stack:
                top = stack.pop()
                on_stack.remove(top)
                scc.append(top)
                if top == v:
                    break
            if len(scc) > 1:
                members = tuple(sorted(scc))
                cycle_edges = [e for src in scc for e in edges.get(src, []) if e.target in scc]
                cycles.append(Cycle(members=members, edges=tuple(cycle_edges)))

    for node in sorted_nodes:
        if node not in indices:
            strongconnect(node)

    return sorted(cycles, key=lambda c: (len(c.members), c.members[0]))


def _find_module_target(candidate: str, known_modules: dict[str, ModuleInfo]) -> str | None:
    if candidate in known_modules:
        return candidate
    parts = candidate.split(".")
    for i in range(len(parts) - 1, 0, -1):
        prefix = ".".join(parts[:i])
        if prefix in known_modules:
            return prefix
    return None


def build_graph(index: SourceIndex, app_package: str | None = None) -> ImportGraph:
    """Build application internal module import graph from SourceIndex."""
    graph = ImportGraph()
    known = index.modules
    graph.nodes.update(known)

    base_pkgs = {app_package} if app_package else {m.partition(".")[0] for m in known if m}

    for mod_name, mod_info in known.items():
        package = _package_of(mod_name, mod_info.path)
        edges: list[ImportEdge] = []
        seen: set[str] = set()

        for node in _walk_ast(mod_info.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = _find_module_target(alias.name, known)
                    if (
                        target
                        and target != mod_name
                        and target not in seen
                        and any(target == p or target.startswith(f"{p}.") for p in base_pkgs)
                    ):
                        seen.add(target)
                        edges.append(ImportEdge(mod_name, target, node.lineno, mod_info.path))
            elif isinstance(node, ast.ImportFrom):
                base_target = _resolve_relative(package, node.level, node.module)
                if not base_target:
                    continue
                for alias in node.names:
                    combined = f"{base_target}.{alias.name}" if base_target else alias.name
                    target = _find_module_target(combined, known) or _find_module_target(base_target, known)
                    if (
                        target
                        and target != mod_name
                        and target not in seen
                        and any(target == p or target.startswith(f"{p}.") for p in base_pkgs)
                    ):
                        seen.add(target)
                        edges.append(ImportEdge(mod_name, target, node.lineno, mod_info.path))

        graph.edges[mod_name] = edges

    return graph
