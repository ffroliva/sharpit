from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext
    from sharpit.settings import SharpitSettings

from sharpit.engine.collectors.agentsessions.parser import Layout
from sharpit.engine.collectors.agentsessions.store import SessionStore


@dataclass(frozen=True)
class AgentSessionSettings:
    enabled: str = "AUTO"
    session_state_dir: str | None = None
    max_events_per_session: int = 2000
    max_sessions: int = 100
    max_parsed_sessions: int = 100
    stream_debounce: float = 0.4
    allow_raw_reveal: bool = False


def copilot_settings(settings: SharpitSettings) -> AgentSessionSettings:
    return AgentSessionSettings(
        enabled=settings.copilot_enabled,
        session_state_dir=settings.copilot_session_state_dir,
        max_events_per_session=settings.copilot_max_events_per_session,
        max_sessions=settings.copilot_max_sessions,
        max_parsed_sessions=settings.copilot_max_parsed_sessions,
        stream_debounce=settings.copilot_stream_debounce,
        allow_raw_reveal=settings.copilot_allow_raw_reveal,
    )


def claude_code_settings(settings: SharpitSettings) -> AgentSessionSettings:
    return AgentSessionSettings(
        enabled=settings.claude_code_enabled,
        session_state_dir=settings.claude_code_session_state_dir,
        max_events_per_session=settings.claude_code_max_events_per_session,
        max_sessions=settings.claude_code_max_sessions,
        max_parsed_sessions=settings.claude_code_max_parsed_sessions,
        stream_debounce=settings.claude_code_stream_debounce,
        allow_raw_reveal=settings.claude_code_allow_raw_reveal,
    )


def session_store(ctx: SharpitContext, layout: Layout) -> SessionStore:
    key = f"agent_session_store_{layout.name.lower()}"

    def _create() -> SessionStore:
        s = copilot_settings(ctx.settings) if layout == Layout.COPILOT else claude_code_settings(ctx.settings)
        return SessionStore(s, layout)

    return ctx.lazy(key, _create)
