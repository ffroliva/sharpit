"""Safe bounded file and text operations for static security analysis."""

from __future__ import annotations

import os
import stat
from pathlib import Path

MAX_FILE_BYTES = 1_048_576  # 1 MiB


def _is_symlink_or_junction(path: Path) -> bool:
    try:
        lst = os.lstat(path)
        if stat.S_ISLNK(lst.st_mode):
            return True
        return os.path.isjunction(path)
    except FileNotFoundError:
        return False
    except OSError:
        return True


def _is_outside_root(root: Path, target: Path) -> bool:
    root_norm = os.path.normcase(str(root))
    target_norm = os.path.normcase(str(target))
    try:
        return os.path.commonpath([root_norm, target_norm]) != root_norm
    except ValueError:
        return True


def contains_symbolic_link(trusted_root: Path, candidate: Path) -> bool:
    """True if candidate climbs outside trusted_root or any segment along the path is a symlink/junction."""
    root = Path(os.path.abspath(trusted_root))
    target = Path(os.path.abspath(candidate))

    if _is_outside_root(root, target):
        return True

    try:
        rel = target.relative_to(root)
    except ValueError:
        return True

    current = root
    for segment in rel.parts:
        current = current / segment
        if _is_symlink_or_junction(current):
            return True
    return False


def _validate_lstat(trusted_root: Path, path: Path) -> os.stat_result:
    if contains_symbolic_link(trusted_root, path):
        raise ValueError("Symlink or junction detected")
    try:
        lst = os.lstat(path)
    except OSError as exc:
        raise ValueError("Cannot stat file") from exc

    if not stat.S_ISREG(lst.st_mode):
        raise ValueError("File is not a regular file")
    if lst.st_size > MAX_FILE_BYTES:
        raise ValueError("File size exceeds inspection limit")
    return lst


def _read_fd_bounded(fd: int, lst: os.stat_result) -> bytes:
    fst = os.fstat(fd)
    if not stat.S_ISREG(fst.st_mode) or not os.path.samestat(lst, fst):
        raise ValueError("File changed or is not regular")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(65536, MAX_FILE_BYTES + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > MAX_FILE_BYTES:
            raise ValueError("File size exceeds inspection limit")
    return b"".join(chunks)


def read_bounded(trusted_root: Path, path: Path) -> bytes:
    """Read a regular file under trusted_root safely within MAX_FILE_BYTES without following symlinks/junctions."""
    lst = _validate_lstat(trusted_root, path)
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValueError("Cannot open file") from exc
    try:
        return _read_fd_bounded(fd, lst)
    finally:
        os.close(fd)


def read_text(trusted_root: Path, path: Path, errors: str = "strict") -> str:
    """Read bounded text as UTF-8 (BOM stripped); any decode error raises ValueError when errors='strict'."""
    data = read_bounded(trusted_root, path)
    try:
        return data.decode("utf-8-sig", errors=errors)
    except UnicodeDecodeError as exc:
        raise ValueError("File is not valid UTF-8") from exc


def _handle_in_quote(
    c: str, text: str, i: int, quote: str, escaped: bool, out: list[str]
) -> tuple[int, str | None, bool]:
    out.append(c)
    if quote == '"' and c == "\\" and not escaped:
        return i, quote, True
    if c == quote and not escaped:
        if quote == "'" and i + 1 < len(text) and text[i + 1] == "'":
            i += 1
            out.append(text[i])
            return i, quote, False
        return i, None, False
    return i, quote, False


def _is_quote_start(text: str, i: int, c: str) -> bool:
    if c not in ('"', "'"):
        return False
    return i == 0 or text[i - 1] != "\\"


def _is_comment_start(text: str, i: int, c: str) -> bool:
    if c != "#":
        return False
    return i == 0 or text[i - 1].isspace()


def _skip_yaml_comment(text: str, i: int, out: list[str]) -> int:
    n = len(text)
    while i < n and text[i] != "\n":
        i += 1
    if i < n:
        out.append("\n")
    return i


def strip_yaml_comments(text: str) -> str:
    """Strip YAML comments preserving line counts and quoted content (port of BootUI stripYamlComments)."""
    out: list[str] = []
    quote: str | None = None
    escaped = False
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if quote is not None:
            i, quote, escaped = _handle_in_quote(c, text, i, quote, escaped, out)
        elif _is_quote_start(text, i, c):
            quote = c
            out.append(c)
        elif _is_comment_start(text, i, c):
            i = _skip_yaml_comment(text, i, out)
        else:
            out.append(c)
        i += 1
    return "".join(out)
