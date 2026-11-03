"""Bounded, read-only index of the host application's source (spec §4.2). Never imports or executes it."""

from __future__ import annotations

import ast
import os  # noqa: F401 - red skeleton; the index walks with it
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

MAX_FILES = 2000
MAX_FILE_BYTES = 524_288


@dataclass(frozen=True)
class ModuleInfo:
    name: str
    path: Path
    tree: ast.Module
    imports: tuple[str, ...]
    functions: tuple[str, ...]


@dataclass
class SourceIndex:
    modules: dict[str, ModuleInfo] = field(default_factory=dict[str, ModuleInfo])
    limitations: list[str] = field(default_factory=list[str])
    truncated: bool = False


def resolve_package_root(
    app: object,
    modules: Mapping[str, object],
    *,
    app_package: str | None = None,
    search_path: Sequence[str] = (),
    reasons: list[str] | None = None,
) -> Path | None:
    return None


def build_index(
    root: Path,
    *,
    max_files: int = MAX_FILES,
    max_file_bytes: int = MAX_FILE_BYTES,
    wall_budget_s: float = 10.0,
    thread: bool = True,
) -> SourceIndex:
    return SourceIndex()
