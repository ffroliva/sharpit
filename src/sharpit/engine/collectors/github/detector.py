from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Repository:
    owner: str
    name: str
    full_name: str
    host: str
    api_base_uri: str
    html_url: str
    local_branch: str | None
    upstream_branch: str | None


def detect_repository(_start: Path, _allowed_hosts: frozenset[str]) -> str:
    return "No local git repository was detected"
