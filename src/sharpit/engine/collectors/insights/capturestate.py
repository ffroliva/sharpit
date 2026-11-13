"""One capture-state type for every recorder a check can depend on (BootUI ``insights/SqlCapture.java`` shape)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True)
class CaptureState:
    """``reason`` is why nothing is recorded; ``None`` means it is. One field, so no state is illegal."""

    reason: str | None

    @property
    def recorded(self) -> bool:
        return self.reason is None

    @classmethod
    def capturing(cls) -> Self:
        return cls(None)

    @classmethod
    def not_recorded(cls, reason: str) -> Self:
        return cls(reason)
