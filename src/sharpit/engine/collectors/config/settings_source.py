"""pydantic-settings provenance: which source supplied each settings field (no side effects)."""

import importlib
import types
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union, cast, get_args, get_origin

_MISSING = object()


@dataclass
class ConfigEntry:
    name: str
    value: object
    source: str
    description: str | None
    default: object
    secret_typed: bool


def _paths(value: object) -> list[Path]:
    if value is None:
        return []
    if isinstance(value, (str, Path)):
        return [Path(value)]
    return [Path(cast(str, v)) for v in cast(list[object], value) if v is not None]


def _classes(annotation: object) -> list[type]:
    """Concrete classes inside ``annotation`` (unwrapping Optional/Union)."""
    if get_origin(annotation) in (Union, types.UnionType):
        return [t for a in get_args(annotation) for t in _classes(a)]
    return [annotation] if isinstance(annotation, type) else []


def _default(field: Any) -> object:
    try:
        return field.get_default(call_default_factory=True)
    except Exception:  # factories that need validated data have no static default
        return None


def _same(value: object, default: object) -> bool:
    try:
        return (value == default) is True
    except Exception:
        return False


def _call(source: Any) -> Mapping[str, Any]:
    try:
        return source()
    except Exception:  # a broken source must not hide the others
        return {}


def settings_entries(instance: object, environ: Mapping[str, str]) -> tuple[list[ConfigEntry], list[str]]:
    """Never raises: on unexpected failure falls back to default/init attribution per field."""
    try:
        return _settings_entries(instance, environ)
    except Exception:
        pass
    try:
        from pydantic_settings import BaseSettings

        if not isinstance(instance, BaseSettings):
            return [], []
        cls = type(instance)
        prefix = str(cls.model_config.get("env_prefix") or "")
        fallback: list[ConfigEntry] = []
        for fname, field in cls.model_fields.items():
            value, default = getattr(instance, fname, None), _default(field)
            label = f"{'default' if _same(value, default) else 'init'} ({cls.__name__})"
            fallback.append(ConfigEntry((prefix + fname).upper(), value, label, field.description, default, False))
        return fallback, []
    except Exception:
        return [], []


def _settings_entries(instance: object, environ: Mapping[str, str]) -> tuple[list[ConfigEntry], list[str]]:
    try:
        from pydantic import BaseModel, SecretBytes, SecretStr
        from pydantic_settings import BaseSettings, DotEnvSettingsSource, EnvSettingsSource, SecretsSettingsSource
    except ImportError:
        return [], []
    try:
        parse_env_vars: Any = importlib.import_module("pydantic_settings.sources.utils").parse_env_vars
    except ImportError:  # older pydantic-settings keeps it in a flat ``sources`` module
        parse_env_vars = importlib.import_module("pydantic_settings.sources").parse_env_vars
    if not isinstance(instance, BaseSettings):
        return [], []
    cls = type(instance)
    cfg = cls.model_config

    class _Env(EnvSettingsSource):
        def _load_env_vars(self) -> Mapping[str, str | None]:  # the given mapping, never os.environ
            return parse_env_vars(environ, self.case_sensitive, self.env_ignore_empty, self.env_parse_none_str)

    env_src = _Env(cls)
    sources: list[tuple[str, Mapping[str, Any]]] = [("systemEnvironment", _call(env_src))]
    for path in reversed(_paths(cfg.get("env_file"))):  # later files win
        data: Mapping[str, Any] = (
            _call(lambda p=path: DotEnvSettingsSource(cls, env_file=p)()) if path.is_file() else {}
        )
        sources.append((f"dotenv: {path}", data))
    for directory in _paths(cfg.get("secrets_dir")):
        data = _call(lambda d=directory: SecretsSettingsSource(cls, secrets_dir=d)()) if directory.is_dir() else {}
        sources.append((f"secrets: {directory}", data))
    custom = cls.settings_customise_sources.__func__ is not BaseSettings.settings_customise_sources.__func__  # pyright: ignore[reportFunctionMemberAccess]
    delimiter = env_src.env_nested_delimiter
    name_of = cls.__name__
    entries: list[ConfigEntry] = []

    def emit(name: str, field: Any, value: object, found: list[Any]) -> None:
        # found[i]: what source i returned for this field, or _MISSING
        default = _default(field)
        models = [m for m in _classes(field.annotation) if issubclass(m, BaseModel)]
        if delimiter and models and isinstance(value, BaseModel):
            for sub, sub_field in type(value).model_fields.items():
                sub_found: list[Any] = [
                    cast(Mapping[str, Any], d).get(sub, _MISSING) if isinstance(d, Mapping) else _MISSING for d in found
                ]
                emit(f"{name}{delimiter}{sub}", sub_field, getattr(value, sub), sub_found)
            return
        label = next((src for (src, _), hit in zip(sources, found, strict=True) if hit is not _MISSING), None)
        if custom:
            label = f"settings ({name_of})"
        elif label is None:
            label = f"{'default' if _same(value, default) else 'init'} ({name_of})"
        secret = any(issubclass(t, (SecretStr, SecretBytes)) for t in _classes(field.annotation))
        secret = secret or isinstance(value, (SecretStr, SecretBytes))
        entries.append(
            ConfigEntry(
                name if cfg.get("case_sensitive") else name.upper(), value, label, field.description, default, secret
            )
        )

    for fname, field in cls.model_fields.items():
        key, env_name, _ = env_src._extract_field_info(field, fname)[0]  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        found = [data.get(key, _MISSING) for _, data in sources]
        emit(env_name, field, getattr(instance, fname), found)
    return entries, [label for label, _ in sources]
