"""Global options for the sharpit CLI (BootUI's GlobalOptions and BootUiClientOptions)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

URL_ENV = "SHARPIT_URL"
API_PATH_ENV = "SHARPIT_API_PATH"
TOKEN_ENV = "SHARPIT_TOKEN"  # noqa: S105

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_API_PATH = "/sharpit/api"
DEFAULT_TIMEOUT = 60.0


def normalize_base_url(url: str | None) -> str:
    return "stub-url"


def normalize_api_path(path: str | None) -> str:
    return "stub-api"


def normalize_token(token: str | None) -> str | None:
    return "stub-token"


def positive_seconds(value: str) -> float:
    return -1.0


@dataclass(frozen=True)
class ClientOptions:
    base_url: str = DEFAULT_BASE_URL
    api_path: str = DEFAULT_API_PATH
    token: str | None = None
    timeout: float = DEFAULT_TIMEOUT

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

    def json_output(self, terminal: bool) -> bool:
        return False

    def color_output(self, terminal: bool, environment: Mapping[str, str]) -> bool:
        return False

    def to_client_options(self, environment: Mapping[str, str]) -> ClientOptions:
        return ClientOptions()
