"""Runtime configuration overrides layer and overrides file store."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import secrets
import threading
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sharpit.engine.masking import Exposure, Masker
from sharpit.settings import SharpitSettings

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

logger = logging.getLogger("sharpit.config.overrides")

_HEADER = "# sharpit local runtime overrides - do not commit.\n"
_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,255}$")
_MAX_VALUE_BYTES = 64 * 1024
_MAX_VALUE_CHARS = 32767  # the Windows environment value limit; one cap for every platform
_MAX_FILE_BYTES = 1024 * 1024
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")

# Names an override must never reach: they steer child processes, the interpreter's loader, TLS and proxy trust,
# credentials, or sharpit's own activation (deviation P-O1). All comparisons are case-insensitive (Windows env
# names are). EXACT names match the whole name; PREFIXES match every name that starts with them (a family).
_REFUSED_EXACT = frozenset(
    {
        "PATH",
        "PATHEXT",
        "COMSPEC",
        "SYSTEMROOT",
        "BASH_ENV",
        "ENV",
        "NODE_OPTIONS",
        "JAVA_TOOL_OPTIONS",
        "_JAVA_OPTIONS",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "GITHUB_TOKEN",
        "GH_TOKEN",
    }
)
_REFUSED_PREFIXES = ("LD_", "DYLD_", "PYTHON")
_DEFAULT_PROFILE_VARS: tuple[str, ...] = SharpitSettings().profile_vars

# Saved pre-override environment values. Module-level on purpose: one ConfigOverrideService exists per process
# (install() builds it), so two instances overriding the same name is not supported.
_ORIGINAL_ENVIRON: dict[str, str | None] = {}
_LOCK = threading.Lock()


class RefusedNameError(ValueError):
    """The name is valid but policy forbids overriding it."""


class OverridesFileError(RuntimeError):
    """The overrides file cannot be written, or must not be (it was malformed or held entries sharpit skipped)."""


def _is_sharpit_key(name: str) -> bool:
    upper = name.upper()
    lower = name.lower()
    return upper.startswith("SHARPIT_") or lower.startswith("sharpit.") or upper == "SHARPIT" or lower == "sharpit"


def _is_refused_name(name: str, profile_vars: Iterable[str]) -> bool:
    upper = name.upper()
    if upper in _REFUSED_EXACT or upper.startswith(_REFUSED_PREFIXES):
        return True
    return any(upper == var.strip().upper() for var in (*_DEFAULT_PROFILE_VARS, *profile_vars))


def _validate_name(name: object, profile_vars: Iterable[str] = ()) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Property name must not be blank")
    trimmed = name.strip()
    if not _NAME_PATTERN.fullmatch(trimmed):
        raise ValueError("Property name is invalid")  # never echoes the text: it may be a pasted secret
    if _is_sharpit_key(trimmed):
        raise RefusedNameError("sharpit settings cannot be overridden at runtime.")
    if _is_refused_name(trimmed, profile_vars):
        raise RefusedNameError("Environment variable cannot be overridden at runtime.")
    return trimmed


def _validate_value(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Property value must be a string")
    if len(value) > _MAX_VALUE_CHARS:
        raise ValueError(f"Property value must not exceed {_MAX_VALUE_CHARS} characters")
    try:
        encoded = value.encode("utf-8")  # strict: refuses a lone surrogate on every platform
        os.fsencode(value)
    except UnicodeEncodeError as e:
        raise ValueError("Property value cannot be stored in the environment") from e
    if len(encoded) > _MAX_VALUE_BYTES:
        raise ValueError("Property value must not exceed 64 KiB")
    if _CONTROL_CHARS.search(value):
        raise ValueError("Property value must not contain control characters or newlines")
    return value


def validate_entry(name: object, value: object, profile_vars: Iterable[str] = ()) -> tuple[str, str]:
    """The one check for an override entry, used by ``put`` and by the startup/constructor loader."""
    checked = _validate_name(name, profile_vars), _validate_value(value)
    # Windows caps the whole ``name=value`` string at 32767 UTF-16 code units, not the value alone
    if os.name == "nt" and len(checked[0]) + 1 + len(checked[1].encode("utf-16-le")) // 2 > _MAX_VALUE_CHARS:
        raise ValueError(f"Property name and value must not exceed {_MAX_VALUE_CHARS} UTF-16 units together")
    return checked


def _restore_env(name: str, prior: str | None) -> None:
    with contextlib.suppress(Exception):
        if prior is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = prior


def _env_key(name: str) -> str:
    return name.upper() if os.name == "nt" else name


@dataclass(frozen=True)
class ConfigOverrideResult:
    name: str
    value: str | None
    previous_value: str | None
    persisted: bool
    message: str

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
        """Parse the file. Raises ``ValueError`` (never echoing a line's content) or ``RuntimeError`` on I/O."""
        try:
            if not self._file.exists():
                return {}
            if self._file.stat().st_size > _MAX_FILE_BYTES:
                raise ValueError("Overrides file exceeds 1 MiB")
            content = self._file.read_text(encoding="utf-8-sig")
        except OSError as e:
            raise RuntimeError(f"Unable to read sharpit overrides file: {self._file}") from e
        except UnicodeDecodeError as e:
            raise ValueError("Overrides file is not valid UTF-8") from e

        result: dict[str, str] = {}
        for line_num, line in enumerate(content.splitlines(), start=1):
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                continue
            result.update(self._parse_line(line_num, line_str))
        return result

    @staticmethod
    def _parse_line(line_num: int, line: str) -> dict[str, str]:
        prefix = f"Malformed line {line_num} in overrides file"
        if "=" not in line:
            raise ValueError(f"{prefix}: missing '='")
        name, _, raw_value = line.partition("=")
        name = name.strip()
        if not _NAME_PATTERN.fullmatch(name):
            raise ValueError(f"{prefix}: invalid name")
        try:
            value = json.loads(raw_value.strip())
        except ValueError as e:
            raise ValueError(f"{prefix}: value is not valid JSON") from e
        if not isinstance(value, str):
            raise ValueError(f"{prefix}: value must be a JSON string")
        return {name: value}

    def save(self, overrides: Mapping[str, Any]) -> None:
        file = self._file
        parent = file.parent
        temp_path = parent / f".{file.name}.tmp.{secrets.token_hex(8)}"
        created = False
        try:
            parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(temp_path, flags, 0o600)
            created = True
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(_HEADER)
                for k, v in overrides.items():
                    val_str = "" if v is None else str(v)
                    f.write(f"{k}={json.dumps(val_str)}\n")
            os.replace(temp_path, file)
        except OSError as e:
            if created:
                with contextlib.suppress(OSError):
                    temp_path.unlink()
            raise OverridesFileError(f"Unable to write sharpit overrides file: {file}") from e

    def delete(self) -> None:
        try:
            if self._file.exists():
                self._file.unlink()
        except OSError as e:
            raise OverridesFileError(f"Unable to delete sharpit overrides file: {self._file}") from e


def load_overrides(path: str | Path, profile_vars: Iterable[str] = ()) -> tuple[dict[str, str], list[str]]:
    """Validate every entry of the overrides file; never raises.

    A malformed file, or one entry that fails validation, yields no entries and one warning (all or nothing). A name
    that policy refuses is skipped and named in a warning; the rest still load. Warnings never carry a line's content.
    """
    file_path = Path(path)
    try:
        raw = ConfigOverridesFileStore(file_path).load()
    except (OSError, RuntimeError, ValueError) as e:
        return {}, [f"Ignoring malformed overrides file {file_path}: {e}"]
    extra = tuple(profile_vars)
    entries: dict[str, str] = {}
    keys: set[str] = set()
    skipped: list[str] = []
    for name, value in raw.items():
        try:
            valid_name, valid_value = validate_entry(name, value, extra)
        except RefusedNameError:
            skipped.append(name)
        except ValueError as e:
            return {}, [f"Ignoring overrides file {file_path}: entry '{name}': {e}"]
        else:
            if _env_key(valid_name) in keys:
                return {}, [f"Ignoring overrides file {file_path}: entry '{name}': duplicate name"]
            keys.add(_env_key(valid_name))
            entries[valid_name] = valid_value
    warnings = [f"Overrides file {file_path}: refused names skipped: {', '.join(skipped)}"] if skipped else []
    return entries, warnings


def _resolve_overrides_file(settings: SharpitSettings | None, overrides_file: str | Path | None) -> Path:
    if overrides_file is not None and str(overrides_file).strip():
        return Path(str(overrides_file).strip())
    if settings is not None and getattr(settings, "overrides_file", None):
        return Path(settings.overrides_file)
    if settings is not None and getattr(settings, "state_dir", None):
        return Path(f"{settings.state_dir}/overrides.env")
    return Path(".sharpit/overrides.env")


def _build_masker(
    settings: SharpitSettings | None, expose_values: str | Exposure | None, mask_secrets: bool | None
) -> Masker:
    if settings is not None:
        exp_val = expose_values if expose_values is not None else settings.expose_values
        ms_val = mask_secrets if mask_secrets is not None else settings.mask_secrets
        tok_val = settings.authentication_token
    else:
        exp_val = expose_values if expose_values is not None else "MASKED"
        ms_val = mask_secrets if mask_secrets is not None else True
        tok_val = None
    return Masker(Exposure(exp_val), ms_val, token=tok_val)


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
        self._file = _resolve_overrides_file(settings, overrides_file)
        self._store = ConfigOverridesFileStore(self._file)
        self._profile_vars: tuple[str, ...] = tuple(settings.profile_vars) if settings is not None else ()
        self._masker = masker if masker is not None else _build_masker(settings, expose_values, mask_secrets)

        self._overrides, self._load_warnings = load_overrides(self._file, self._profile_vars)

    def _require_intact_file(self) -> None:
        """A save writes only the in-memory map: refuse it when the file held entries that map does not."""
        if self._load_warnings:
            raise OverridesFileError(
                f"Overrides file {self._file} is malformed; fix or delete it, then restart the app"
            )

    @property
    def overrides_file(self) -> Path:
        return self._file

    @property
    def store(self) -> ConfigOverridesFileStore:
        return self._store

    @property
    def load_warnings(self) -> list[str]:
        return list(self._load_warnings)

    def overrides(self) -> dict[str, str]:
        return dict(self._overrides)

    def has_override(self, name: str) -> bool:
        return self._alias(name) is not None

    def _alias(self, name: str) -> str | None:
        """The layer's own spelling of ``name``; on Windows ``Path`` and ``PATH`` are one variable."""
        if name in self._overrides:
            return name
        key = _env_key(name)
        return next((n for n in self._overrides if _env_key(n) == key), None)

    def _save_or_rollback(self, snapshot: dict[str, str]) -> None:
        try:
            self._store.save(self._overrides)
        except Exception as e:
            self._overrides = snapshot
            if isinstance(e, OverridesFileError):
                raise
            raise OverridesFileError(f"Unable to write sharpit overrides file: {self._file}") from e

    def put(self, name: str, value: object) -> ConfigOverrideResult:
        validated_name, validated_value = validate_entry(name, "" if value is None else value, self._profile_vars)
        self._require_intact_file()
        with _LOCK:
            alias = self._alias(validated_name)
            previous = self._overrides.get(alias) if alias is not None else None
            previous_display = self._display_value(validated_name, previous)
            snapshot = dict(self._overrides)
            if alias is not None and alias != validated_name:
                del self._overrides[alias]
            self._overrides[validated_name] = validated_value
            key = _env_key(validated_name)
            had_original = key in _ORIGINAL_ENVIRON
            prior = os.environ.get(validated_name)
            try:
                _ORIGINAL_ENVIRON.setdefault(key, prior)
                os.environ[validated_name] = validated_value
                self._store.save(self._overrides)
            except Exception as e:
                self._overrides = snapshot
                _restore_env(validated_name, prior)
                if not had_original:
                    _ORIGINAL_ENVIRON.pop(key, None)
                if isinstance(e, OverridesFileError):
                    raise
                raise OverridesFileError(f"Unable to write sharpit overrides file: {self._file}") from e
        return ConfigOverrideResult(
            name=validated_name,
            value=self._display_value(validated_name, validated_value),
            previous_value=previous_display,
            persisted=True,
            message=self._describe_rebind_caveat(),
        )

    def remove(self, name: str) -> ConfigOverrideResult:
        validated_name = _validate_name(name, self._profile_vars)
        self._require_intact_file()
        with _LOCK:
            alias = self._alias(validated_name)
            if alias is None:
                return ConfigOverrideResult(
                    name=validated_name,
                    value=None,
                    previous_value=None,
                    persisted=True,
                    message=self._describe_rebind_caveat(),
                )
            previous = self._overrides[alias]
            snapshot = dict(self._overrides)
            del self._overrides[alias]
            self._save_or_rollback(snapshot)
            key = _env_key(alias)
            if key in _ORIGINAL_ENVIRON:
                orig = _ORIGINAL_ENVIRON.pop(key)
                if orig is None:
                    os.environ.pop(alias, None)
                else:
                    os.environ[alias] = orig
        return ConfigOverrideResult(
            name=validated_name,
            value=None,
            previous_value=self._display_value(validated_name, previous),
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


def apply_overrides_file(path: str | Path, profile_vars: Iterable[str] = ()) -> list[str]:
    """Apply the file's entries to ``os.environ`` at startup, all or nothing; never raises. Returns warnings."""
    entries, warnings = load_overrides(path, profile_vars)
    applied: list[tuple[str, str | None, bool]] = []
    with _LOCK:
        try:
            for name, value in entries.items():
                key = _env_key(name)
                prior = os.environ.get(name)
                applied.append((name, prior, key in _ORIGINAL_ENVIRON))
                _ORIGINAL_ENVIRON.setdefault(key, prior)
                os.environ[name] = value
        except Exception:
            for name, prior, had_original in reversed(applied):
                _restore_env(name, prior)
                if not had_original:
                    _ORIGINAL_ENVIRON.pop(_env_key(name), None)
            warnings.append(f"Ignoring overrides file {path}: the environment refused an entry; nothing applied")
    return warnings


def override_service(ctx: SharpitContext) -> ConfigOverrideService:
    """The one service of this install: the routes write through it, the config report reads its flags."""
    return ctx.lazy("config.overrides", lambda: ConfigOverrideService(ctx.settings, masker=ctx.masker))
