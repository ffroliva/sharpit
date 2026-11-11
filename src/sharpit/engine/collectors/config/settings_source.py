"""pydantic-settings provenance: which source supplied each settings field (no side effects)."""

import contextlib
import dataclasses
import datetime
import decimal
import importlib
import json
import pathlib
import types
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Literal, Union, cast, get_args, get_origin

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
    except Exception:  # noqa: S110 - the docstring's promise: falls back below
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


_SAFE_SCALARS: tuple[type, ...] = (
    str,
    int,
    float,
    bool,
    type(None),
    pathlib.Path,
    datetime.datetime,
    datetime.date,
    datetime.time,
    datetime.timedelta,
    decimal.Decimal,
    uuid.UUID,
)


def is_json_marker(metadata: object) -> bool:
    """Whether an ``Annotated`` metadata item is pydantic's ``Json`` (``Json[X]`` is ``Annotated[X, Json]``)."""
    try:
        from pydantic import Json
    except ImportError:
        return False
    return metadata is Json or isinstance(metadata, cast(type, Json))


def is_provably_safe(annotation: object) -> bool:
    """Whether an annotation is provably free of secrets (allow-list of plain scalars)."""
    if annotation is None or annotation is type(None):
        return True
    origin = get_origin(annotation)
    if origin is Annotated:
        args = get_args(annotation)
        # Json[...] anywhere is never provably safe, whatever its inner type
        return bool(args) and not any(is_json_marker(m) for m in args[1:]) and is_provably_safe(args[0])
    if origin in (Union, types.UnionType):
        args = get_args(annotation)
        if not args:
            return False
        return all(is_provably_safe(arg) for arg in args)
    if origin is Literal:
        return True
    if origin in (list, tuple, set, frozenset):
        args = get_args(annotation)
        if not args:
            return False
        return all(is_provably_safe(arg) for arg in args if arg is not Ellipsis)
    if isinstance(annotation, type) and annotation in _SAFE_SCALARS:
        return True
    return bool(isinstance(annotation, type) and issubclass(annotation, Enum))


_PLAIN: tuple[object, ...] = (str, int, float, bool, type(None))


def compound_shape(annotation: object) -> tuple[bool, list[type[Enum]]]:
    """For an allow-listed annotation: whether Configuration renders its value as compound text (anything but a plain
    str/int/float/bool), and the Enum classes among its leaves (Configuration shows a member as ``Cls.NAME``)."""
    origin = get_origin(annotation)
    args = [a for a in get_args(annotation) if a is not Ellipsis]
    if origin is Annotated:  # Json[...] and other metadata: checked as compound, the safe side
        return True, compound_shape(args[0])[1] if args else []
    if origin is Literal:
        return False, []
    if origin in (Union, types.UnionType, list, tuple, set, frozenset):
        shapes = [compound_shape(a) for a in args]
        enums = [e for _, es in shapes for e in es]
        return origin not in (Union, types.UnionType) or any(c for c, _ in shapes), enums
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return True, [annotation]
    return annotation not in _PLAIN, []


def is_secret_scalar(annotation: object) -> bool:
    """Whether an annotation represents a plain secret scalar (SecretStr, SecretBytes, Secret[...])."""
    if annotation is None or annotation is type(None):
        return False
    origin = get_origin(annotation)
    if origin is Annotated:
        args = get_args(annotation)
        return is_secret_scalar(args[0]) if args else False
    if origin in (Union, types.UnionType):
        args = [a for a in get_args(annotation) if a is not None and a is not type(None)]
        return bool(args) and any(is_secret_scalar(a) for a in args)
    try:
        import pydantic
        from pydantic import SecretBytes, SecretStr
    except ImportError:
        return False
    Secret = getattr(pydantic, "Secret", None)
    if origin is not None and Secret is not None and origin is Secret:
        return True
    if isinstance(annotation, type):
        if issubclass(annotation, (SecretStr, SecretBytes)):
            return True
        if Secret is not None and issubclass(annotation, Secret):
            return True
    return False


class KeySafety(Enum):
    SAFE = "SAFE"
    UNSAFE_SCALAR = "UNSAFE_SCALAR"
    UNSAFE_COMPLEX = "UNSAFE_COMPLEX"


@dataclass
class ModelFieldRule:
    exact_names: set[str] = dataclasses.field(default_factory=set[str])
    delimited_prefixes: set[str] = dataclasses.field(default_factory=set[str])
    case_sensitive: bool = False
    is_safe: bool = False
    is_secret_scalar: bool = False
    # every name the field answers to; may over-include env_prefix + fname on an aliased field (only masks more)
    names: set[str] = dataclasses.field(default_factory=set[str])
    value_checked: bool = False  # allow-listed but compound: Configuration masks by the value's text
    enums: list[type[Enum]] = dataclasses.field(default_factory=list[type[Enum]])


@dataclass
class ProfileSourceDescriptor:
    path: Path
    encoding: str = "utf-8"
    rules: list[ModelFieldRule] = dataclasses.field(default_factory=list[ModelFieldRule])

    def _matches(self, key: str) -> list[tuple[ModelFieldRule, bool]]:
        """Every rule the key matches, across all models declaring this file, with whether it matched exactly."""
        matched: list[tuple[ModelFieldRule, bool]] = []
        for rule in self.rules:
            test_key = key if rule.case_sensitive else key.upper()
            if test_key in rule.exact_names:
                matched.append((rule, True))
            elif any(test_key.startswith(prefix) for prefix in rule.delimited_prefixes):
                matched.append((rule, False))
        return matched

    def classify(self, key: str) -> KeySafety:
        unsafe = [(rule, exact) for rule, exact in self._matches(key) if not rule.is_safe]
        if not unsafe:
            return KeySafety.SAFE
        if all(exact and rule.is_secret_scalar for rule, exact in unsafe):
            return KeySafety.UNSAFE_SCALAR
        return KeySafety.UNSAFE_COMPLEX

    def field_names(self, key: str) -> set[str]:
        """Every name the fields matching ``key`` answer to; Configuration masks by these, not the .env key."""
        return {name for rule, _ in self._matches(key) for name in rule.names}

    def value_texts(self, key: str, value: str | None) -> list[str]:
        """The texts Configuration's compound check sees for a compound allow-listed field; [] for a plain one."""
        rules = [rule for rule, _ in self._matches(key) if rule.value_checked]
        if not rules or value is None:
            return []
        tokens = {value}
        with contextlib.suppress(ValueError, RecursionError):
            parsed = json.loads(value)
            if isinstance(parsed, list):
                tokens |= {str(item) for item in cast(list[object], parsed)}
        members = [m for rule in rules for e in rule.enums for m in e if m.name in tokens or str(m.value) in tokens]
        return [value, *(str(m) for m in members)]


def parse_env(content: str) -> list[tuple[str, str | None]]:
    """Parse .env content using python-dotenv without interpolation."""
    try:
        from dotenv import dotenv_values
    except ImportError:
        return []
    import io

    data = dotenv_values(stream=io.StringIO(content), interpolate=False)
    return list(data.items())


def _model_rules(cls: type[Any]) -> list[ModelFieldRule]:
    try:
        from pydantic_settings import BaseSettings, EnvSettingsSource
    except ImportError:
        return []

    if not issubclass(cls, BaseSettings):
        return []

    cfg = getattr(cls, "model_config", None)
    case_sensitive = bool(
        cast(Mapping[str, object], cfg).get("case_sensitive", False)
        if isinstance(cfg, Mapping)
        else getattr(cfg, "case_sensitive", False)
    )
    env_prefix = str(
        cast(Mapping[str, object], cfg).get("env_prefix", "")
        if isinstance(cfg, Mapping)
        else getattr(cfg, "env_prefix", "") or ""
    )

    class _Env(EnvSettingsSource):
        def _load_env_vars(self) -> Mapping[str, str | None]:
            return {}

    env_src = _Env(cls)
    delimiter = env_src.env_nested_delimiter

    rules: list[ModelFieldRule] = []

    for fname, field in cls.model_fields.items():
        # FieldInfo moves a top-level Annotated's metadata (a top-level Json[...]) out of the annotation
        is_safe = is_provably_safe(field.annotation) and not any(is_json_marker(m) for m in field.metadata)
        secret_scalar = is_secret_scalar(field.annotation)
        value_checked, enums = compound_shape(field.annotation) if is_safe else (False, [])

        candidate_names: set[str] = set()
        candidate_names.add(fname)
        candidate_names.add(fname.upper())
        candidate_names.add(fname.lower())
        if env_prefix:
            candidate_names.add(f"{env_prefix}{fname}")
            candidate_names.add(f"{env_prefix}{fname}".upper())
            candidate_names.add(f"{env_prefix}{fname}".lower())

        if field.alias:
            candidate_names.add(field.alias)

        val_alias = getattr(field, "validation_alias", None)
        if isinstance(val_alias, str):
            candidate_names.add(val_alias)
        elif val_alias is not None and hasattr(val_alias, "choices"):
            for c in getattr(val_alias, "choices", []):
                if isinstance(c, str):
                    candidate_names.add(c)

        with contextlib.suppress(Exception):
            for item in env_src._extract_field_info(field, fname):  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
                if item[0]:
                    candidate_names.add(item[0])
                if item[1]:
                    candidate_names.add(item[1])

        norm_exact: set[str] = set()
        norm_delim: set[str] = set()
        for name in candidate_names:
            norm_name = name if case_sensitive else name.upper()
            norm_exact.add(norm_name)
            if delimiter:
                delim_prefix = f"{name}{delimiter}"
                norm_delim.add(delim_prefix if case_sensitive else delim_prefix.upper())

        rules.append(
            ModelFieldRule(
                exact_names=norm_exact,
                delimited_prefixes=norm_delim,
                case_sensitive=case_sensitive,
                is_safe=is_safe,
                is_secret_scalar=secret_scalar,
                names=candidate_names,
                value_checked=value_checked,
                enums=enums,
            )
        )

    return rules


def declared_profile_sources(models: Iterable[object]) -> list[ProfileSourceDescriptor]:
    """All declared profile sources with their encoding and field safety rules."""
    try:
        from pydantic_settings import BaseSettings
    except ImportError:
        return []
    result: list[ProfileSourceDescriptor] = []
    by_path: dict[Path, ProfileSourceDescriptor] = {}
    for m in models:
        cls = m if isinstance(m, type) else type(m)
        if not issubclass(cls, BaseSettings):
            continue
        cfg = getattr(cls, "model_config", None)
        env_file = (
            cast(Mapping[str, object], cfg).get("env_file")
            if isinstance(cfg, Mapping)
            else getattr(cfg, "env_file", None)
        )
        raw_encoding = (
            cast(Mapping[str, object], cfg).get("env_file_encoding")
            if isinstance(cfg, Mapping)
            else getattr(cfg, "env_file_encoding", None)
        )
        encoding = str(raw_encoding or "utf-8")
        rules = _model_rules(cls)

        for p in _paths(env_file):
            if p not in by_path:
                desc = ProfileSourceDescriptor(p, encoding, list(rules))
                by_path[p] = desc
                result.append(desc)
            else:
                by_path[p].rules.extend(rules)
    return result


def declared_env_files(models: Iterable[object]) -> list[Path]:
    """All env_file paths declared across the given pydantic-settings models."""
    return [s.path for s in declared_profile_sources(models)]
