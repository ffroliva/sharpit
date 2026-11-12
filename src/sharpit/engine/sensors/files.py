"""STUB for the red commit: records nothing."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any

SOURCE = "files"


class FilesSensor:
    name = SOURCE
    events = ("open", "os.remove", "os.rename", "shutil.copyfile")
    ignored = 0

    def __init__(
        self,
        mask_path: Callable[[str], str] = lambda path: path,
        *,
        own: Iterable[str] = (),
        cwd: str | None = None,
        home: str | None = None,
        tmp: str | None = None,
    ) -> None:
        del mask_path, own, cwd, home, tmp

    def record(self, event: str, args: tuple[Any, ...]) -> tuple[Mapping[str, object], ...]:
        del event, args
        return ()
