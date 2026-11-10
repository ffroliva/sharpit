"""Security facts extracted from FastAPI and Starlette internals without invoking app code."""

from __future__ import annotations

import inspect
import re
from typing import Any, cast
from urllib.parse import urlsplit

from sharpit.engine.spi import MiddlewareFacts, SchemeUrl

from .introspection_common import MAX_DEPTH, OWN_MODULE_PREFIX, as_objects, attrs, dotted

_LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})
_PROBE_ORIGINS = ("https://attacker.invalid", "http://evil.example.net")
_FLOW_FIELDS = ("authorizationUrl", "tokenUrl", "refreshUrl")


def _strings(value: object) -> tuple[str, ...]:
    """Exact ``str``/``list``/``tuple``/``set``/``frozenset`` only: a user subclass's ``__iter__`` never runs."""
    if type(value) is str:
        return tuple(part.strip() for part in value.split(","))
    if type(value) in (list, tuple, set, frozenset):
        return tuple(item for item in cast("tuple[object, ...]", tuple(cast("Any", value))) if type(item) is str)
    return ()


def _broad_regex(pattern: object) -> bool:
    if type(pattern) is not str:
        return False
    try:
        compiled = re.compile(pattern)
    except re.error:
        return False
    return any(compiled.fullmatch(origin) is not None for origin in _PROBE_ORIGINS)


def _cors_flags(options: dict[str, object]) -> set[str]:
    flags: set[str] = set()
    if "*" in _strings(options.get("allow_origins")):
        flags.add("any_origin")
    if options.get("allow_credentials") is True:
        flags.add("credentials")
    if _broad_regex(options.get("allow_origin_regex")):
        flags.add("broad_origin_regex")
    return flags


_SECRET_FIELDS = {("starlette.datastructures", "Secret"): "_value", ("pydantic.types", "SecretStr"): "_secret_value"}


def _secret_text(value: object) -> object:
    """A Starlette ``Secret`` or pydantic ``SecretStr`` unwrapped from its instance dict (no ``str()`` runs)."""
    field = _SECRET_FIELDS.get((type(value).__module__, type(value).__qualname__))
    return attrs(value).get(field) if field is not None else value


def _session_flags(options: dict[str, object]) -> set[str]:
    flags: set[str] = set()
    if options.get("https_only") is True:
        flags.add("https_only")
    same_site = options.get("same_site")
    if type(same_site) is str and same_site.lower() == "none":
        flags.add("same_site_none")
    secret = _secret_text(options.get("secret_key"))
    if type(secret) is str and len(secret) < 32:  # noqa: PLR2004 - the length is the fact; never the value
        flags.add("short_secret")
    return flags


def _host_flags(options: dict[str, object]) -> set[str]:
    hosts = options.get("allowed_hosts")
    return {"any_host"} if hosts is None or "*" in _strings(hosts) else set()


def _proxy_flags(options: dict[str, object]) -> set[str]:
    return {"trust_any_proxy"} if "*" in _strings(options.get("trusted_hosts", "127.0.0.1")) else set()


FLAG_READERS = {
    "CORSMiddleware": _cors_flags,
    "SessionMiddleware": _session_flags,
    "TrustedHostMiddleware": _host_flags,
    "ProxyHeadersMiddleware": _proxy_flags,
}


def _option_flags(name: str, options: dict[str, object]) -> tuple[str, ...]:
    reader = FLAG_READERS.get(name.rpartition(".")[2])
    return tuple(sorted(reader(options))) if reader is not None else ()


def middleware_facts(app: object, limitations: list[str], mount: str | None = None) -> tuple[MiddlewareFacts, ...]:
    entries: Any = inspect.getattr_static(app, "user_middleware", None)
    listed: list[object] = list(cast(list[object], entries)) if type(entries) is list else []
    found: list[MiddlewareFacts] = []
    for entry in listed:
        values = attrs(entry)
        cls = values.get("cls")
        if cls is None or str(attrs(cls).get("__module__", "")).startswith(OWN_MODULE_PREFIX):  # sharpit's own: hidden
            continue
        name = dotted(cls)
        options = values.get("kwargs")
        if values.get("args"):
            limitations.append(f"{name.rpartition('.')[2]} options passed positionally were not read.")
        found.append(
            MiddlewareFacts(
                name, _option_flags(name, cast(dict[str, object], options) if type(options) is dict else {}), mount
            )
        )
    return tuple(found)


def scheme_objects(node: object, depth: int, base: type, out: dict[int, object]) -> None:
    call: object = getattr(node, "call", None)  # FastAPI's slotted ``Dependant``, as ``_schemes_in`` reads it
    if issubclass(type(call), base):
        out.setdefault(id(call), call)
        return
    if depth < MAX_DEPTH:
        for sub in as_objects(getattr(node, "dependencies", None)):
            scheme_objects(sub, depth + 1, base, out)


def _insecure_url(value: object) -> bool:
    if type(value) is not str:
        return False
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
    except ValueError:
        return False
    return parts.scheme.lower() == "http" and bool(host) and host not in _LOOPBACK and not host.endswith(".localhost")


def scheme_urls(scheme: object) -> list[SchemeUrl]:
    name = dotted(type(scheme))
    model = attrs(attrs(scheme).get("model"))
    found: list[SchemeUrl] = []
    if "openIdConnectUrl" in model:
        found.append(SchemeUrl(name, "openIdConnectUrl", _insecure_url(model["openIdConnectUrl"])))
    for flow in attrs(model.get("flows")).values():
        flow_values = attrs(flow)
        found.extend(SchemeUrl(name, f, _insecure_url(flow_values[f])) for f in _FLOW_FIELDS if f in flow_values)
    return found
