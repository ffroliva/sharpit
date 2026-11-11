"""Runtime configuration overrides layer and overrides file store."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sharpit.engine.masking import Exposure, Masker
from sharpit.settings import SharpitSettings

logger = logging.getLogger("sharpit.config.overrides")

_HEADER = "# sharpit local runtime overrides - do not commit.\n"
_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,255}$")
_REFUSED_LOADER_VARS = frozenset(
    {
        "PATH",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONSTARTUP",
        "PYTHONINSPECT",
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
    }
)

_ORIGINAL_ENVIRON: dict[str, str | None] = {}


def _is_sharpit_key(name: str) -> bool:
    upper = name.upper()
    lower = name.lower()
    return upper.startswith("SHARPIT_") or lower.startswith("sharpit.") or upper == "SHARPIT" or lower == "sharpit"


def _is_loader_var(name: str) -> bool:
    return name in _REFUSED_LOADER_VARS or name.startswith("DYLD_")


def _validate_name(name: str | None) -> str:
    if name is None or not name.strip():
        raise ValueError("Property name must not be blank")
    trimmed = name.strip()
    if not _NAME_PATTERN.fullmatch(trimmed):
        raise ValueError(f"Property name '{trimmed}' is invalid")
    if _is_sharpit_key(trimmed):
        raise ValueError("sharpit settings cannot be overridden at runtime.")
    if _is_loader_var(trimmed):
        raise ValueError(f"Environment variable '{trimmed}' cannot be overridden at runtime.")
    return trimmed


def _validate_value(value: object) -> str:
    val_str = "" if value is None else str(value)
    if len(val_str.encode("utf-8")) > 64 * 1024:
        raise ValueError("Property value must not exceed 64 KiB")
    if "\n" in val_str or "\r" in val_str or "\0" in val_str:
        raise ValueError("Property value must not contain control characters or newlines")
    return val_str


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
        if not self._file.exists():
            return {}
        try:
            content = self._file.read_text(encoding="utf-8")
        except OSError as e:
            raise RuntimeError(f"Unable to read sharpit overrides file: {self._file}") from e

        result: dict[str, str] = {}
        for line_num, line in enumerate(content.splitlines(), start=1):
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                continue
            if "=" not in line_str:
                raise ValueError(f"Malformed line {line_num} in overrides file: missing '='")
            name, _, raw_value = line_str.partition("=")
            name = name.strip()
            raw_value = raw_value.strip()
            if not _NAME_PATTERN.fullmatch(name):
                raise ValueError(f"Malformed line {line_num} in overrides file: invalid name '{name}'")
            try:
                val = json.loads(raw_value)
                if not isinstance(val, str):
                    val = str(val)
            except Exception as e:
                raise ValueError(f"Malformed line {line_num} in overrides file: {e}") from e
            result[name] = val
        return result

    def save(self, overrides: Mapping[str, Any]) -> None:
        file = self._file
        parent = file.parent
        if parent:
            parent.mkdir(parents=True, exist_ok=True)
        temp_path = parent / f".{file.name}.tmp.{secrets.token_hex(4)}"
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            mode = 0o600
            fd = os.open(temp_path, flags, mode)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(_HEADER)
                for k, v in overrides.items():
                    val_str = "" if v is None else str(v)
                    f.write(f"{k}={json.dumps(val_str)}\n")
            if os.name != "nt":
                with contextlib.suppress(OSError):
                    os.chmod(temp_path, 0o600)
            os.replace(temp_path, file)
        except OSError as e:
            if temp_path.exists():
                with contextlib.suppress(OSError):
                    temp_path.unlink()
            raise RuntimeError(f"Unable to write sharpit overrides file: {file}") from e

    def delete(self) -> None:
        try:
            if self._file.exists():
                self._file.unlink()
        except OSError as e:
            raise RuntimeError(f"Unable to delete sharpit overrides file: {self._file}") from e


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
        self._settings = settings
        if overrides_file is not None and str(overrides_file).strip():
            self._file = Path(str(overrides_file).strip())
        elif settings is not None and getattr(settings, "overrides_file", None):
            self._file = Path(settings.overrides_file)
        elif settings is not None and getattr(settings, "state_dir", None):
            self._file = Path(f"{settings.state_dir}/overrides.env")
        else:
            self._file = Path(".sharpit/overrides.env")

        self._store = ConfigOverridesFileStore(self._file)

        if masker is not None:
            self._masker = masker
        else:
            if settings is not None:
                exp_val = expose_values if expose_values is not None else settings.expose_values
                ms_val = mask_secrets if mask_secrets is not None else settings.mask_secrets
                tok_val = settings.authentication_token
            else:
                exp_val = expose_values if expose_values is not None else "MASKED"
                ms_val = mask_secrets if mask_secrets is not None else True
                tok_val = None
            exposure = Exposure(exp_val)
            self._masker = Masker(exposure, ms_val, token=tok_val)

        self._overrides: dict[str, str] = self._store.load() if self._file.exists() else {}

    @property
    def overrides_file(self) -> Path:
        return self._file

    @property
    def store(self) -> ConfigOverridesFileStore:
        return self._store

    def overrides(self) -> dict[str, str]:
        return dict(self._overrides)

    def has_override(self, name: str) -> bool:
        return name in self._overrides

    def hasOverride(self, name: str) -> bool:
        return self.has_override(name)

    def put(self, name: str, value: object, persist: bool = True) -> ConfigOverrideResult:
        validated_name = _validate_name(name)
        validated_value = _validate_value(value)

        previous = self._overrides.get(validated_name)
        previous_display = self._display_value(validated_name, previous) if previous is not None else None

        if validated_name not in _ORIGINAL_ENVIRON:
            _ORIGINAL_ENVIRON[validated_name] = os.environ.get(validated_name)

        self._overrides[validated_name] = validated_value
        try:
            self._store.save(self._overrides)
        except Exception as e:
            if previous is None:
                self._overrides.pop(validated_name, None)
            else:
                self._overrides[validated_name] = previous
            if not (isinstance(e, RuntimeError) and "Unable to write sharpit overrides file" in str(e)):
                raise RuntimeError(f"Unable to write sharpit overrides file: {self._file}") from e
            raise

        os.environ[validated_name] = validated_value
        display = self._display_value(validated_name, validated_value)
        return ConfigOverrideResult(
            name=validated_name,
            value=display,
            previous_value=previous_display,
            persisted=True,
            message=self._describe_rebind_caveat(),
        )

    def remove(self, name: str) -> ConfigOverrideResult:
        validated_name = _validate_name(name)
        if validated_name not in self._overrides:
            return ConfigOverrideResult(
                name=validated_name,
                value=None,
                previous_value=None,
                persisted=True,
                message=self._describe_rebind_caveat(),
            )

        previous = self._overrides[validated_name]
        previous_display = self._display_value(validated_name, previous)
        del self._overrides[validated_name]

        try:
            self._store.save(self._overrides)
        except Exception as e:
            self._overrides[validated_name] = previous
            if not (isinstance(e, RuntimeError) and "Unable to write sharpit overrides file" in str(e)):
                raise RuntimeError(f"Unable to write sharpit overrides file: {self._file}") from e
            raise

        orig = _ORIGINAL_ENVIRON.pop(validated_name, None)
        if orig is None:
            os.environ.pop(validated_name, None)
        else:
            os.environ[validated_name] = orig

        return ConfigOverrideResult(
            name=validated_name,
            value=None,
            previous_value=previous_display,
            persisted=True,
            message=self._describe_rebind_caveat(),
        )

    def _display_value(self, name: str, value: str | None) -> str | None:
        if value is None:
            return None
        masked, _ = self._masker.mask(name, value)
        return None if masked is None else str(masked)

    def _describe_rebind_caveat(self) -> str:
        return (
            f"Override stored at {self._file}. Settings objects already created may keep their previous value "
            "until restart."
        )


def apply_overrides_file(path: str | Path) -> list[str]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    store = ConfigOverridesFileStore(file_path)
    try:
        entries = store.load()
    except Exception as e:
        return [f"Ignoring malformed overrides file {file_path}: {e}"]

    for name, value in entries.items():
        if _is_sharpit_key(name) or _is_loader_var(name):
            continue
        if name not in _ORIGINAL_ENVIRON:
            _ORIGINAL_ENVIRON[name] = os.environ.get(name)
        os.environ[name] = value
    return []
