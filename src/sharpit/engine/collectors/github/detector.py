"""Read a local Git origin without invoking git or contacting the remote."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

_SCP_REMOTE = re.compile(r"(?:[^@]+@)?([^:]+):(.+)")
_NO_REPOSITORY = "No local git repository was detected"
_NO_ORIGIN = "No GitHub origin remote was detected"
_NOT_GITHUB = "Origin remote host is not github.com or an allowed GitHub Enterprise host"


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


@dataclass(frozen=True)
class _GitLayout:
    git_dir: Path
    config_paths: tuple[Path, ...]


def detect_repository(start: Path, allowed_hosts: frozenset[str]) -> Repository | str:
    layout = _find_git_layout(start)
    if layout is None:
        return _NO_REPOSITORY
    config = _read_config(layout.config_paths)
    remote = _parse_remote(config.get(('remote "origin"', "url")))
    if remote is None:
        return _NO_ORIGIN
    host, owner, name = remote
    host = host.lower()
    allowed = {value.lower() for value in allowed_hosts}
    if host not in {"github.com", "ssh.github.com", *allowed}:
        return _NOT_GITHUB
    github = host in {"github.com", "ssh.github.com"}
    html_host = "github.com" if host == "ssh.github.com" else host
    branch = _read_branch(layout.git_dir)
    merge = config.get((f'branch "{branch}"', "merge")) if branch is not None else None
    upstream = merge.removeprefix("refs/heads/") if merge is not None else None
    return Repository(
        owner,
        name,
        f"{owner}/{name}",
        host,
        "https://api.github.com/" if github else f"https://{host}/api/v3/",
        f"https://{html_host}/{owner}/{name}",
        branch,
        upstream,
    )


def _find_git_layout(start: Path) -> _GitLayout | None:
    current = start.resolve()
    while True:
        dot_git = current / ".git"
        git_dir = dot_git if dot_git.is_dir() else _read_pointer(dot_git, "gitdir:") if dot_git.is_file() else None
        if git_dir is not None:
            paths = [git_dir / "config"]
            common = _read_pointer(git_dir / "commondir", "") if (git_dir / "commondir").is_file() else None
            if common is not None and common / "config" not in paths:
                paths.append(common / "config")
            return _GitLayout(git_dir, tuple(paths))
        if current.parent == current:
            return None
        current = current.parent


def _read_pointer(path: Path, prefix: str) -> Path | None:
    """A ``.git`` file's ``gitdir:`` or a ``commondir`` file's path, resolved against the file's own directory."""
    try:
        line = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    if not line.startswith(prefix):
        return None
    target = Path(line[len(prefix) :].strip())
    return (target if target.is_absolute() else path.parent / target).resolve()


def _read_config(paths: tuple[Path, ...]) -> dict[tuple[str, str], str]:
    values: dict[tuple[str, str], str] = {}
    for path in paths:
        if not path.is_file():
            continue
        try:
            section: str | None = None
            for raw in path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith(("#", ";")):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    section = line[1:-1]
                elif section is not None and (equals := line.find("=")) > 0:
                    values[(section, line[:equals].strip())] = line[equals + 1 :].strip()
        except (OSError, UnicodeError):
            return {}
    return values


def _read_branch(git_dir: Path) -> str | None:
    try:
        value = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None
    prefix = "ref: refs/heads/"
    return value.removeprefix(prefix) if value.startswith(prefix) else None


def _parse_remote(value: str | None) -> tuple[str, str, str] | None:
    if not value:
        return None
    host: str
    path: str
    if value.startswith(("http://", "https://", "ssh://")):
        try:
            parsed = urlsplit(value)
            host, path = parsed.hostname or "", parsed.path
        except ValueError:
            return None
    else:
        match = _SCP_REMOTE.fullmatch(value)
        if match is None:
            return None
        host, path = match.groups()
    segments = path.lstrip("/").removesuffix(".git").split("/")
    if not host or len(segments) < 2 or not segments[0] or not segments[1]:
        return None
    return host, segments[0], segments[1]
