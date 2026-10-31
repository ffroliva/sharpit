"""Dev-server signal (the DevTools equivalent, spec 7.4). Parses argv only: no fastapi import, no side effects."""

from __future__ import annotations

from collections.abc import Sequence


def dev_server_signal(argv: Sequence[str]) -> str | None:
    """Name of the reloading dev server this process was started by, or None.

    Programmatic ``uvicorn.run(..., reload=True)`` is not detected (argv shows only the script); set a profile.
    """
    if "--reload" in argv[1:]:
        return "uvicorn --reload"
    if len(argv) > 1 and argv[1] == "dev":
        parts = argv[0].replace("\\", "/").lower().split("/")  # Windows paths too: PurePath is OS-specific
        if parts[-1] in {"fastapi", "fastapi.exe"} or parts[-2:] == ["fastapi", "__main__.py"]:
            return "fastapi dev"
    return None
