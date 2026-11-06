"""Stable, local-keyed identities for SQLite statement shapes.

The key file is only ever seen whole: a creator writes a temporary file beside it and renames that into place, under an
OS lock the kernel drops if the creator dies, so a crash leaves nothing a reader can take for a key and no stale lock.
"""

from __future__ import annotations

import errno
import hashlib
import hmac
import os
import secrets
import sys
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

KEY_NAME = "identity.key"
KEY_BYTES = 32
IGNORED = ("identity.key", "identity.key.lock", "identity.key.*")  # a temporary file holds a whole key until rename
WAIT_SECONDS = 10.0  # for the lock, and on Windows for a reader holding a bad file open


def fingerprint(shape_text: str, key: bytes | None) -> str | None:
    if key is None:
        return None
    return hmac.new(key, shape_text.encode("utf-8", "surrogatepass"), hashlib.sha256).hexdigest()


def load_key(
    state_dir: Path, *, create: bool, on_error: Callable[[OSError | ValueError], None] | None = None
) -> bytes | None:
    """The key, or None: no file, a bad file or a link. ``create=True`` only from an active install or a session start.

    Only a creator replaces a bad file, a good one is never written, and a link is refused either way.
    """
    path = state_dir / KEY_NAME
    try:
        return _read_or_create(state_dir, path) if create else _read(path)
    except (OSError, ValueError) as exc:  # a NUL in the path is a ValueError
        if on_error is not None:
            on_error(exc)
        return None


def _read_or_create(state_dir: Path, path: Path) -> bytes | None:
    return _create(state_dir, path)


def _read(path: Path) -> bytes | None:
    """``O_NOFOLLOW`` where the platform has it. Windows has none: the lstat alone refuses there, a check then a use."""
    if path.is_symlink():
        raise OSError(errno.ELOOP, "refusing a symlink", str(path))
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return None
    with os.fdopen(fd, "rb") as stream:
        key = stream.read(KEY_BYTES + 1)
    return key if len(key) == KEY_BYTES else None


def _create(state_dir: Path, path: Path) -> bytes | None:
    state_dir.mkdir(parents=True, exist_ok=True)
    _preflight_ignore(state_dir)
    with _exclusive(path):
        key = _read(path)
        _ignore_the_key(state_dir)
        if key is not None:
            return key
        _publish(path)
        return _read(path)


def _preflight_ignore(state_dir: Path) -> None:
    ignore = state_dir / ".gitignore"
    if ignore.is_symlink():
        raise OSError(errno.ELOOP, "refusing a symlink", str(ignore))
    if ignore.exists():
        with ignore.open("ab"):
            pass


def _ignore_the_key(state_dir: Path) -> None:
    """Keep both key paths ignored before returning or publishing one (owner's ruling)."""
    ignore = state_dir / ".gitignore"
    if ignore.is_symlink():
        raise OSError(errno.ELOOP, "refusing a symlink", str(ignore))
    content = ignore.read_bytes() if ignore.exists() else b""
    lines = [line[:-1] if line.endswith(b"\r") else line for line in content.split(b"\n")]
    missing: list[bytes] = []
    for name in IGNORED:
        pattern = name.encode()
        if not any(
            line == pattern and not any(later.startswith(b"!") for later in lines[index + 1 :])
            for index, line in enumerate(lines)
        ):
            missing.append(pattern)
    if not missing:
        return
    prefix = b"" if not content or content.endswith(b"\n") else b"\n"
    with ignore.open("ab") as stream:
        stream.write(prefix + b"".join(name + b"\n" for name in missing))


def _publish(path: Path) -> None:
    temporary = path.with_name(f"{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(secrets.token_bytes(KEY_BYTES))
        _patiently(lambda: os.replace(temporary, path))
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _exclusive(path: Path) -> Generator[None]:
    """One creator at a time: two that each replaced a bad file would hand their workers two keys."""
    fd = os.open(path.with_name(f"{path.name}.lock"), os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        _patiently(lambda: _lock(fd))
        yield
    finally:
        os.close(fd)  # drops the lock on both platforms


def _lock(fd: int) -> None:
    if sys.platform == "win32":
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _patiently(action: Callable[[], None]) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    while True:
        try:
            action()
        except OSError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.002)
        else:
            return
