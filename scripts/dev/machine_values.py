"""Machine values collector and leak gate feeder."""

from __future__ import annotations

import argparse
import getpass
import os
import shutil
import socket
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

COMMON_SYSTEM_VALUES = frozenset(
    {
        "Windows_NT",
        "ProgramFiles",
        "ProgramFiles(x86)",
        "CommonProgramFiles",
        "CommonProgramFiles(x86)",
        "SystemRoot",
        "SystemDrive",
        "System32",
        "LOCALAPPDATA",
        "ALLUSERSPROFILE",
        "PUBLIC",
        "ProgramData",
        "AMD64",
        "x86_64",
        "PROCESSOR_ARCHITECTURE",
        "C:\\Windows",
        "C:\\Windows\\System32",
        "C:\\Windows\\system32",
        "/usr/bin",
        "/usr/local/bin",
        "/usr/sbin",
        "/bin",
        "/sbin",
        "localhost",
        "127.0.0.1",
        "true",
        "false",
        "None",
    }
)


def _git_config(key: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "config", key],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        val = proc.stdout.strip()
        return val if proc.returncode == 0 and val else None
    except OSError:
        return None


def _git_remotes() -> list[str]:
    urls: list[str] = []
    try:
        proc = subprocess.run(
            ["git", "config", "--get-regexp", r"^remote\..*\.url"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2 and parts[1]:
                    urls.append(parts[1])
    except OSError:
        pass
    return urls


def _gh_login() -> str | None:
    if not shutil.which("gh"):
        return None
    try:
        proc = subprocess.run(
            ["gh", "api", "user", "-q", ".login"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        val = proc.stdout.strip()
        return val if proc.returncode == 0 and val else None
    except OSError:
        return None


def _env_entries(env: dict[str, str]) -> list[str]:
    entries: list[str] = []
    for key, val in env.items():
        if "PATH" in key.upper() or os.pathsep in val:
            entries.extend(val.split(os.pathsep))
        else:
            entries.append(val)
    return entries


def _system_user_and_host() -> list[str]:
    vals: list[str] = []
    try:
        user = getpass.getuser()
        if user:
            vals.append(user)
    except OSError:
        pass
    try:
        hostname = socket.gethostname()
        if hostname:
            vals.append(hostname)
    except OSError:
        pass
    return vals


def _git_identity() -> list[str]:
    vals: list[str] = []
    email = _git_config("user.email")
    if email:
        vals.append(email)
    name = _git_config("user.name")
    if name:
        vals.append(name)
    gh_user = _gh_login()
    if gh_user:
        vals.append(gh_user)
    return vals


def _clean_values(raw_values: list[str]) -> list[str]:
    cleaned: list[str] = []
    for item in raw_values:
        val = item.strip().strip("'\"")
        if len(val) >= 6 and val not in COMMON_SYSTEM_VALUES:
            cleaned.append(val)
    return list(dict.fromkeys(cleaned))


def collect_machine_values(env: dict[str, str] | None = None) -> list[str]:
    """Collect sensitive machine identifiers to guard against leaks in fixtures."""
    target_env = env if env is not None else dict(os.environ)
    raw_values: list[str] = []

    raw_values.extend(_system_user_and_host())
    for key in ("USERPROFILE", "HOME"):
        val = target_env.get(key)
        if val:
            raw_values.append(val)

    raw_values.extend(_git_identity())
    raw_values.extend(_git_remotes())
    raw_values.extend(_env_entries(target_env))

    return _clean_values(raw_values)


def write_machine_values(
    out_path: Path | str,
    values: Sequence[str] | None = None,
    env: dict[str, str] | None = None,
) -> Path:
    """Write machine values one per line to out_path, refusing locations inside the repo."""
    resolved = Path(out_path).resolve()
    repo_root = REPO_ROOT.resolve()
    if resolved == repo_root or repo_root in resolved.parents or resolved.is_relative_to(repo_root):
        raise ValueError(f"Output path must not be inside the git repo root: {out_path}")

    vals = list(values) if values is not None else collect_machine_values(env)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text("\n".join(vals) + "\n", encoding="utf-8")
    return resolved


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect machine values for leak gate.")
    parser.add_argument("--out", required=True, help="Output file path (must be outside repo).")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    write_machine_values(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
