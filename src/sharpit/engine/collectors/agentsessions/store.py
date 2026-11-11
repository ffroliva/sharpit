from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sharpit.engine.collectors.agentsessions import AgentSessionSettings, Layout

from sharpit.engine.collectors.agentsessions.dashboard import build_dashboard
from sharpit.engine.collectors.agentsessions.parser import Layout


def resolve_dir(configured: str | None, default_sub: str) -> Path:
    if not configured or not configured.strip():
        return (Path.home() / default_sub).resolve()
    return Path(os.path.expanduser(configured.strip())).resolve()


def display_session_dir(path: Path, configured: str | None = None) -> str:
    return "/unimplemented/path"


class SessionStore:
    def __init__(self, settings: AgentSessionSettings, layout: Layout, clock: Any = None) -> None:
        self.settings = settings
        self.layout = layout
        self.clock = clock
        self._lock = threading.Lock()
        default_sub = ".copilot/session-state" if layout == Layout.COPILOT else ".claude/projects"
        self._default_dir_str = f"~/{default_sub}"
        self._source_name = "Copilot CLI" if layout == Layout.COPILOT else "Claude Code"
        self._panel_title = "Copilot" if layout == Layout.COPILOT else "Claude Code"
        self.dir_path = resolve_dir(settings.session_state_dir, default_sub)
        self.display_dir = "/unimplemented/path"
        self._sessions: dict[str, Any] = {}

    def is_directory_available(self) -> bool:
        return False

    def refresh(self) -> None:
        pass

    def sessions(self, since: int | None = None, until: int | None = None) -> dict[str, Any]:
        return {
            "available": False,
            "unavailableReason": "Unimplemented",
            "sessionStateDir": "/unimplemented/path",
            "total": -1,
            "returned": -1,
            "maxSessions": -1,
            "sessions": [],
            "warnings": [],
        }

    def dashboard(self) -> dict[str, Any]:
        return build_dashboard(
            sessions=[],
            available=False,
            unavailable_reason="Unimplemented",
            session_state_dir="/unimplemented/path",
        )

    def detail(self, session_id: str) -> dict[str, Any] | None:
        return None

    def events(
        self, session_id: str, category: str | None = None, since: int | None = None, limit: int = 200
    ) -> dict[str, Any] | None:
        return None

    def raw(self, session_id: str, event_id: str) -> None:
        return None
