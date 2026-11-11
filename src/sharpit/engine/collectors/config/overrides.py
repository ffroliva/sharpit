"""Runtime configuration overrides layer and overrides file store."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sharpit.engine.masking import Exposure, Masker
from sharpit.settings import SharpitSettings


@dataclass(frozen=True)
class ConfigOverrideResult:
    name: str
    value: str | None
    previous_value: str | None
    persisted: bool
    message: str

    @property
    def previousValue(self) -> str | None:
        return self.previous_value

    def to_dto(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "previousValue": self.previous_value,
            "persisted": self.persisted,
            "message": self.message,
        }


class ConfigOverridesFileStore:
    def __init__(self, file: str | Path) -> None:
        self._file = Path(file)

    @property
    def file(self) -> Path:
        return self._file

    def load(self) -> dict[str, str]:
        return {"stub": "not_implemented"}

    def save(self, overrides: Any) -> None:
        pass

    def delete(self) -> None:
        pass


class ConfigOverrideService:
    def __init__(
        self,
        settings: SharpitSettings | None = None,
        *,
        overrides_file: str | Path | None = None,
        masker: Masker | None = None,
        expose_values: str | Exposure | None = None,
        mask_secrets: bool | None = None,
    ) -> None:
        self._file = Path("stub_overrides.env")
        self._store = ConfigOverridesFileStore(self._file)

    @property
    def overrides_file(self) -> Path:
        return self._file

    @property
    def store(self) -> ConfigOverridesFileStore:
        return self._store

    def overrides(self) -> dict[str, str]:
        return {"stub": "data"}

    def has_override(self, name: str) -> bool:
        return False

    def put(self, name: str, value: str, persist: bool = True) -> ConfigOverrideResult:
        return ConfigOverrideResult(
            name="stub",
            value="stub",
            previous_value="stub",
            persisted=False,
            message="stub",
        )

    def remove(self, name: str) -> ConfigOverrideResult:
        return ConfigOverrideResult(
            name="stub",
            value="stub",
            previous_value="stub",
            persisted=False,
            message="stub",
        )


def apply_overrides_file(path: str | Path) -> list[str]:
    return []
