"""Dev-services restart through the docker CLI (W8 D1), as BootUI ``DevServicesService.restart`` (:157-184).

The container id comes only from the recorded snapshot (``find``), never from request text. Returns ``(status, body)``;
the route adds nothing but the JSON response.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from . import devservices_cli

DISABLED = "Restart is disabled. Set SHARPIT_DEV_SERVICES_RESTART_ENABLED=true to allow it."
UNSUPPORTED = "Service does not support restart"
NOT_FOUND = "Service not found"
FAILED = "Failed to restart service"
RESTARTED = "Service restarted. Already-created clients may need an application restart to reconnect."


@dataclass(frozen=True)
class RecordedService:
    id: str
    container_id: str | None


def _refuse(status: int, message: str) -> tuple[int, dict[str, str]]:
    return status, {"message": message}


def restart(
    service_id: str,
    *,
    enabled: bool,
    find: Callable[[str], RecordedService | None],
    mask: Callable[[str | None], str | None],
    resolve: Callable[[], str | None] = devservices_cli.resolve_docker,
    run: Callable[[str, str], devservices_cli.CliResult] = devservices_cli.docker_restart,
) -> tuple[int, dict[str, str]]:
    service = find(service_id)
    if service is None:
        return _refuse(404, NOT_FOUND)
    if not enabled:
        return _refuse(409, DISABLED)
    container_id = service.container_id
    if not container_id:
        return _refuse(409, UNSUPPORTED)
    docker = resolve()
    if docker is None or not devservices_cli.is_container_id(container_id):
        return _refuse(409, UNSUPPORTED)
    try:
        result = run(docker, container_id)
    except OSError:
        return _refuse(500, FAILED)
    if result.returncode == 0:
        return 200, {"id": service_id, "status": "restarted", "message": RESTARTED}
    shown = None if result.timed_out else mask(result.output.strip())
    return _refuse(500, shown or FAILED)
