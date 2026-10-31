"""Dismissed vulnerability rules (port of BootUI ``DismissedRulesStore``).

The file is ``<state_dir>/sharpit.yml`` in BootUI's ``boot-ui.yml`` format: a header comment and a top-level
``dismissedRules:`` block list of ``  - <id>`` lines. Other lines are preserved and the managed section is re-emitted
last. No YAML library: only that minimal block form is read and written. The file and its directory are created on
the first effective ``add`` (a no-op ``remove`` never writes), and every write is atomic (temp file + ``os.replace``).

sharpit deviation: rule ids must match ``<vulnId>::pypi:<name>``; anything else (quotes, newlines, backslashes...) is a
``BadRequest`` raised before the file is touched, so an id can never inject lines into the file.
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
from pathlib import Path

from sharpit.engine.paging import BadRequest

FILE_NAME = "sharpit.yml"
_KEY = "dismissedRules"
_HEADER = "# sharpit configuration (developer-local; safe to delete)."
_RULE_ID = re.compile(r"[A-Za-z0-9._:-]+::pypi:[a-z0-9._-]+")


def rule_id(vuln_id: str, package_name: str) -> str:
    return f"{vuln_id}::pypi:{package_name}"


class DismissalStore:
    def __init__(self, state_dir: Path) -> None:
        self._file = state_dir / FILE_NAME
        self._lock = threading.Lock()
        # parsed ids keyed on the file's (mtime_ns, size): report() polls list(), the file rarely changes
        self._stamp: tuple[int, int] | None = None
        self._ids: list[str] = []

    def list(self) -> list[str]:
        with self._lock:
            return self._load()

    def add(self, rule_id: str) -> list[str]:
        _validate(rule_id)
        with self._lock:
            ids = self._load()
            if rule_id not in ids:
                ids.append(rule_id)
                self._save(ids)
            return ids

    def remove(self, rule_id: str) -> list[str]:
        _validate(rule_id)
        with self._lock:
            ids = self._load()
            if rule_id in ids:
                ids.remove(rule_id)
                self._save(ids)
            return ids

    def _lines(self) -> list[str]:
        try:
            return self._file.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []

    def _load(self) -> list[str]:
        try:
            st = self._file.stat()
            stamp = (st.st_mtime_ns, st.st_size)
        except OSError:
            stamp = None
        if stamp is not None and stamp == self._stamp:
            return list(self._ids)
        ids = self._parse()
        self._stamp, self._ids = stamp, ids
        return list(ids)

    def _parse(self) -> list[str]:
        ids: list[str] = []
        in_section = False
        for line in self._lines():
            if _is_top_level_key(line):
                in_section = _key_of(line) == _KEY
            elif in_section and line.startswith("  - "):
                value = line[4:].strip()
                if value and value not in ids:
                    ids.append(value)
        return ids

    def _save(self, ids: list[str]) -> None:
        preserved: list[str] = []
        in_section = False
        for line in self._lines():
            if line == _HEADER:
                continue
            if _is_top_level_key(line):
                in_section = _key_of(line) == _KEY
                if not in_section:
                    preserved.append(line)
            elif not in_section:
                preserved.append(line)
        while preserved and not preserved[-1].strip():
            preserved.pop()
        content = "".join(f"{line}\n" for line in [_HEADER, *preserved, "", f"{_KEY}:", *(f"  - {i}" for i in ids)])
        self._file.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="sharpit", suffix=".tmp", dir=self._file.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
            os.replace(tmp, self._file)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def _validate(rule_id: str) -> None:
    if not _RULE_ID.fullmatch(rule_id):
        raise BadRequest(f"Invalid rule id '{rule_id}'")


def _is_top_level_key(line: str) -> bool:
    return bool(line.strip()) and not line[0].isspace() and line[0] not in "#-" and ":" in line


def _key_of(line: str) -> str:
    return line.partition(":")[0].strip()
