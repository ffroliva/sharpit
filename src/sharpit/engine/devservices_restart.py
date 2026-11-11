"""Dev-services restart through the docker CLI (stub)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from . import devservices_cli


@dataclass(frozen=True)
class RecordedService:
    id: str
    container_id: str | None


def restart(
    service_id: str,
    *,
    enabled: bool,
    find: Callable[[str], RecordedService | None],
    mask: Callable[[str | None], str | None],
    resolve: Callable[[], str | None] = devservices_cli.resolve_docker,
    run: Callable[[str, str], devservices_cli.CliResult] = devservices_cli.docker_restart,
) -> tuple[int, dict[str, str]]:
    return 200, {"id": service_id, "status": "restarted", "message": ""}
