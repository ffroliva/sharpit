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
IGNORED = "identity.key\nidentity.key.*\n"  # the temporary file holds a whole key until its rename
WAIT_SECONDS = 10.0  # for the lock, and on Windows for a reader holding a bad file open


def fingerprint(shape_text: str, key: bytes | None) -> str | None:
    if key is None:
        return None
    return hmac.new(key, shape_text.encode("utf-8", "surrogatepass"), hashlib.sha256).hexdigest()


def load_key(state_dir: Path, *, create: bool) -> bytes | None:
    """The key, or None: no file, a bad file or a link. ``create=True`` only from an active install or a session start.

    Only a creator replaces a bad file, a good one is never written, and a link is refused either way.
    """
    path = state_dir / KEY_NAME
    try:
        return _read_or_create(state_dir, path) if create else _read(path)
    except (OSError, ValueError):  # a NUL in the path is a ValueError
        return None


def _read_or_create(state_dir: Path, path: Path) -> bytes | None:
    try:
        key = _read(path)
    except PermissionError:  # on Windows, while another creator's rename lands: its lock waits that out
        key = None
    return key if key is not None else _create(state_dir, path)


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
    with _exclusive(path):
        key = _read(path)
        if key is not None:
            return key
        _ignore_the_key(state_dir)
        _publish(path)
        return _read(path)


def _ignore_the_key(state_dir: Path) -> None:
    """Before the key exists, so no crash can leave one a ``git add`` would take (ruling 5)."""
    try:
        fd = os.open(state_dir / ".gitignore", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        return
    with os.fdopen(fd, "w", encoding="ascii", newline="\n") as stream:
        stream.write(IGNORED)


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
    fd = os.open(path.with_name(f"{path.name}.lock"), os.O_RDWR | os.O_CREAT, 0o600)
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
