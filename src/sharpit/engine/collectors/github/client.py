"""Stub: the GitHub REST client lands with the refresh action (W7 Task G2)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sharpit.engine.collectors.github.dashboard import GitHubDashboard
from sharpit.engine.collectors.github.detector import Repository
from sharpit.engine.collectors.github.token import Token
from sharpit.settings import SharpitSettings

MAX_BODY_BYTES = 2 * 1024 * 1024
NETWORK_FAILED = "Network request failed or timed out while refreshing GitHub data."


def no_redirect_opener(*handlers: Any) -> Any:
    return handlers


class GitHubApiClient:
    def __init__(
        self,
        settings: SharpitSettings,
        token: Callable[[float], Token | None],
        opener: Any = None,
        *,
        scrub: Callable[[str | None], str | None],
    ) -> None:
        self._token = token

    def refresh(self, repo: Repository) -> dict[str, Any]:
        return GitHubDashboard._unavailable("not implemented")  # pyright: ignore[reportPrivateUsage]
