"""Mechanical 0.4.0 lane merge gate (stub: the red commit pins its contract)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

GateRunner = Callable[[str, Sequence[str], Path], tuple[int, str]]
PytestRunner = Callable[[Path, Sequence[str], Path], None]


@dataclass(frozen=True)
class Options:
    lane: str
    worktree: Path
    sha: str
    integration: Path
    accept_unverified: bool = False
    no_rerun: bool = False


@dataclass
class Result:
    refusals: list[str] = field(default_factory=list[str])
    unverified: list[str] = field(default_factory=list[str])


def run_gate_command(name: str, command: Sequence[str], cwd: Path) -> tuple[int, str]:
    return 0, ""


def run_pytest_in(integration: Path) -> PytestRunner:
    return lambda tree, nodeids, junit: None


def evaluate(opts: Options, *, run_gate: GateRunner, run_pytest: PytestRunner) -> Result:
    return Result()


def main(argv: Sequence[str] | None = None) -> int:
    return 0
