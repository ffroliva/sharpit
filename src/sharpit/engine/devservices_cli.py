"""The docker CLI gatekeeper: the only module that spawns a process for dev-services restart (stub)."""

from __future__ import annotations

from dataclasses import dataclass

DOCKER_TIMEOUT_S = 0.0
MAX_OUTPUT_BYTES = 0


@dataclass(frozen=True)
class CliResult:
    returncode: int | None
    timed_out: bool
    output: str


def resolve_docker(path_env: str | None = None) -> str | None:
    return "docker"


def run_argv(argv: list[str], timeout: float = DOCKER_TIMEOUT_S) -> CliResult:
    return CliResult(0, False, "")


def docker_restart(docker: str, container_id: str, timeout: float = DOCKER_TIMEOUT_S) -> CliResult:
    return CliResult(0, False, "")
