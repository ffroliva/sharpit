from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AiSettings:
    token_series_minutes: int
    max_recent_chats: int
    show_content_capture_banner: bool
    traces_enabled: bool


def ai_settings(settings: Any) -> AiSettings:
    return AiSettings(
        settings.ai_token_series_minutes,
        settings.ai_max_recent_chats,
        settings.ai_show_content_capture_banner,
        settings.panels["traces"].enabled,
    )


from .usage import ai_chat_detail, ai_chats, ai_overview, ai_tokens  # noqa: E402

__all__ = ["AiSettings", "ai_settings", "ai_chats", "ai_chat_detail", "ai_overview", "ai_tokens"]
