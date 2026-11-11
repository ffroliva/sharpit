from collections.abc import Callable
from pathlib import Path
from typing import Any


class GitHubDashboard:
    def __init__(self, start: Callable[[], Path], _settings: Any, _client: Any = None) -> None:
        self.start = start

    def dashboard(self) -> dict[str, Any]:
        return {
            "available": False,
            "status": "WRONG",
            "unavailableReason": "No local git repository was detected",
            "connected": False,
            "repository": {"fullName": ""},
            "credential": {"source": "none"},
            "copilotUsage": {"unavailableReason": "No GitHub repository is available"},
        }

    def refresh(self) -> dict[str, Any]:
        return self.dashboard()
