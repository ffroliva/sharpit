"""The Side Effects report an agent reads (``SideEffectsService.agentReport`` of BootUI)."""

from __future__ import annotations

from collections.abc import Sequence

# SideEffectsService.LIMITATION_VALUES, _NETWORK and _FILES, BootUI -> sharpit (see the adaptation table, F11)
LIMITATION_VALUES = (
    "A process row shows the command's file name only, never its arguments or its environment, which can hold "
    "secrets. A process row records the start only: its exit status and lifetime are not recorded."
)
LIMITATION_NETWORK = "A network row shows a host and port, never a byte sent or received, nor a URL's path or query."
LIMITATION_FILES = (
    "Files: the interpreter's own files (imports) and sharpit's own state are counted, not recorded per route. "
    "A call site's frames are read once per run and file pattern, so two call sites of one pattern share the "
    "first one's. A file opened without an audit event, as native code may, is not seen. A move or a copy "
    "records its source and its destination."
)
LIMITATION_AGENT_OMITTED = "What the rows of a sensor without listed rows cannot see is left out: query its id for it."


def agent_limitations(limitations: Sequence[str], shown: set[str]) -> list[str]:
    return list(limitations)
