"""Global options for the sharpit CLI (BootUI's GlobalOptions and BootUiClientOptions)."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import dataclass

URL_ENV = "SHARPIT_URL"
API_PATH_ENV = "SHARPIT_API_PATH"
TOKEN_ENV = "SHARPIT_TOKEN"  # noqa: S105

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_API_PATH = "/sharpit/api"
DEFAULT_TIMEOUT = 60.0


_LOCAL_SCHEME = "http"  # a local developer console; BootUI defaults to plain HTTP on localhost too


def normalize_base_url(url: str | None) -> str:
    value = (url or "").strip()
    if not value:
        return DEFAULT_BASE_URL
    if value.startswith(":"):
        value = "localhost" + value
    scheme, separator, _ = value.partition("://")
    if not separator or scheme not in {"http", "https"}:
        value = f"{_LOCAL_SCHEME}://{value}"
    while value.endswith("/") and len(value) > 1:
        value = value[:-1]
    return value


def normalize_api_path(path: str | None) -> str:
    value = (path or "").strip()
    if not value:
        return DEFAULT_API_PATH
    if not value.startswith("/"):
        value = "/" + value
    value = value.rstrip("/")
    return value or DEFAULT_API_PATH


def normalize_token(token: str | None) -> str | None:
    if token is None or not token.strip():
        return None
    return token.strip()


def positive_seconds(value: str) -> float:
    raw = value.strip().lower()
    try:
        if raw.endswith("ms"):
            raw = str(float(raw[:-2]) / 1000)
        elif raw.endswith("s"):
            raw = raw[:-1]
        seconds = float(raw)
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError(f"'{value}' is not a number of seconds") from None
    if not 0 < seconds < float("inf"):  # NaN fails both comparisons
        raise argparse.ArgumentTypeError(f"must be a positive number of seconds, not {value}")
    return seconds


def first(*candidates: str | None) -> str | None:
    for candidate in candidates:
        if candidate is not None and candidate.strip():
            return candidate.strip()
    return None


@dataclass(frozen=True)
class ClientOptions:
    base_url: str = DEFAULT_BASE_URL
    api_path: str = DEFAULT_API_PATH
    token: str | None = None
    timeout: float = DEFAULT_TIMEOUT

    def __post_init__(self) -> None:
        object.__setattr__(self, "token", normalize_token(self.token))

    def __repr__(self) -> str:
        redacted = "******" if self.token else None
        return (
            f"ClientOptions(base_url={self.base_url!r}, api_path={self.api_path!r}, "
            f"token={redacted!r}, timeout={self.timeout})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@dataclass
class GlobalOptions:
    url: str | None = None
    api_path: str | None = None
    token: str | None = None
    timeout: float | None = None
    json: bool = False
    no_color: bool = False
    verbose: bool = False

    def __repr__(self) -> str:
        token = "'******'" if self.token else "None"
        return (
            f"GlobalOptions(url={self.url!r}, api_path={self.api_path!r}, "
            f"token={token}, timeout={self.timeout!r}, "
            f"json={self.json!r}, no_color={self.no_color!r}, verbose={self.verbose!r})"
        )

    def json_output(self, terminal: bool) -> bool:
        return self.json or not terminal

    def color_output(self, terminal: bool, environment: Mapping[str, str]) -> bool:
        return terminal and not self.no_color and "NO_COLOR" not in environment

    def to_client_options(self, environment: Mapping[str, str]) -> ClientOptions:
        raw_url = first(self.url, environment.get(URL_ENV), DEFAULT_BASE_URL)
        raw_api = first(self.api_path, environment.get(API_PATH_ENV), DEFAULT_API_PATH)
        raw_token = first(self.token, environment.get(TOKEN_ENV), None)
        raw_timeout = self.timeout if self.timeout is not None and self.timeout > 0 else DEFAULT_TIMEOUT
        return ClientOptions(
            base_url=normalize_base_url(raw_url),
            api_path=normalize_api_path(raw_api),
            token=normalize_token(raw_token),
            timeout=raw_timeout,
        )
