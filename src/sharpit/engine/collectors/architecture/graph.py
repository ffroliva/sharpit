"""AST import graph and cycle detection for application packages (spec §5.5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sharpit.engine.appsource import SourceIndex


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


@dataclass
class ImportGraph:
    nodes: set[str] = field(default_factory=set)
    edges: dict[str, list[ImportEdge]] = field(default_factory=dict)

    def find_cycles(self) -> list[Cycle]:
        return []

    def find_package_cycles(self) -> list[Cycle]:
        return []


def build_graph(index: SourceIndex, app_package: str | None = None) -> ImportGraph:
    """Skeleton: returns an empty graph."""
    del index, app_package
    return ImportGraph()
