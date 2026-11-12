"""STUB for the red commit: records nothing."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SOURCE = "processes"


class ProcessesSensor:
    name = SOURCE
    events = ("subprocess.Popen", "os.system", "os.exec", "os.spawn", "os.posix_spawn")

    def record(self, event: str, args: tuple[Any, ...]) -> tuple[Mapping[str, object], ...]:
        del event, args
        return ()
