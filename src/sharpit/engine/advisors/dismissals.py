"""Dismissed advisor rules and findings (port of BootUI 2.2.0 ``DismissedRulesStore``).

The file is ``<state_dir>/sharpit.yml`` in BootUI's ``boot-ui.yml`` format: a header comment and two managed
top-level block lists, ``dismissedRules:`` (``  - <id>``) and ``dismissedFindings:`` (``  - <ruleId> <identity>
[n=<note>]``, the note Base64URL without padding, so user text never needs YAML escaping). Other lines are preserved and
the managed sections are re-emitted last. No YAML library: only that minimal block form is read and written. The file
and its directory are created on the first effective write (a no-op never writes), and every write is atomic (temp
file + ``os.replace``). A ``dismissedFindings`` line that is not exactly the written format is ignored, counted and
kept verbatim, so a newer format is never destroyed.

Shared by every advisor (spec §8). sharpit deviation: a rule id must match ``[A-Za-z0-9._:-]{1,200}`` and have an
owning panel (``owning_panel``); anything else (quotes, spaces, slashes, newlines...) is a ``BadRequest`` raised before
the file is touched, so an id can never inject lines into the file. A finding's rule id is that charset, at most 64
characters and owned by an advisor; its identity is at most 512 characters with no whitespace or control character
(sharpit deviation: BootUI's ``[A-Z]...`` rule ids and ``v<n>:`` identities do not fit sharpit's ids).
"""

from __future__ import annotations

import base64
import binascii
import os
import re
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from sharpit.engine.advisors.registry import advisor_for
from sharpit.engine.advisors.retention import AdvisorViolationError
from sharpit.engine.paging import BadRequest

FILE_NAME = "sharpit.yml"
_KEY = "dismissedRules"
_FINDINGS_KEY = "dismissedFindings"
_HEADER = "# sharpit configuration (developer-local; safe to delete)."
_ITEM = "  - "
_NOTE_PREFIX = "n="
NO_PANEL_MESSAGE = "Findings of advisor '{advisor}' are dismissed in sharpit.yml"
_RULE_ID = re.compile(r"[A-Za-z0-9._:-]{1,200}")
_IDENTITY = re.compile(r"[^\s\x00-\x1f\x7f]{1,512}")
_MAX_FINDING_RULE_ID = 64

MAX_FINDINGS: Final[int] = 1000
MAX_NOTE_LENGTH: Final[int] = 200


@dataclass(frozen=True, slots=True)
class DismissedFinding:
    rule_id: str
    identity: str
    note: str | None = None

    def to_dto(self) -> dict[str, str | None]:
        return {"ruleId": self.rule_id, "identity": self.identity, "note": self.note}


@dataclass(frozen=True, slots=True)
class Findings:
    dismissed: list[DismissedFinding]
    ignored: int

    def to_dto(self) -> dict[str, Any]:
        return {"dismissed": [f.to_dto() for f in self.dismissed], "ignored": self.ignored}


@dataclass
class _Contents:
    """One read of the file."""

    rules: list[str] = field(default_factory=list[str])
    findings: dict[tuple[str, str], DismissedFinding] = field(default_factory=dict[tuple[str, str], DismissedFinding])
    ignored: list[str] = field(default_factory=list[str])
    had_rules_key: bool = False

    def view(self) -> Findings:
        return Findings(list(self.findings.values()), len(self.ignored))


def rule_id(vuln_id: str, package_name: str) -> str:
    return f"{vuln_id}::pypi:{package_name}"


def owning_panel(rule_id: str) -> str | None:
    """The panel whose gate covers dismissing ``rule_id``; None for an id no advisor owns (refused with a 400)."""
    if not _RULE_ID.fullmatch(rule_id):
        return None
    spec = advisor_for(rule_id)  # an unported or unknown RAPI- id has no owner
    return spec.panel if spec else None


class DismissalStore:
    def __init__(self, state_dir: Path) -> None:
        self._file = state_dir / FILE_NAME
        self._lock = threading.Lock()
        # parsed contents keyed on the file's (mtime_ns, size): report() polls list(), the file rarely changes
        self._stamp: tuple[int, int] | None = None
        self._contents = _Contents()

    def list(self) -> list[str]:
        with self._lock:
            return list(self._load().rules)

    def add(self, rule_id: str) -> list[str]:
        _validate(rule_id)
        with self._lock:
            contents = self._load()
            if rule_id not in contents.rules:
                contents.rules.append(rule_id)
                self._save(contents)
            return list(contents.rules)

    def remove(self, rule_id: str) -> list[str]:
        _validate(rule_id)
        with self._lock:
            contents = self._load()
            if rule_id in contents.rules:
                contents.rules.remove(rule_id)
                self._save(contents)
            return list(contents.rules)

    def list_findings(self) -> Findings:
        with self._lock:
            return self._load().view()

    def dismiss_finding(self, rule_id: str, identity: str, note: str | None = None) -> Findings:
        """Dismisses one finding or replaces its note; a blank note means none. 400 when invalid, 409 at the cap."""
        _validate_finding(rule_id, identity)
        normalized = None if note is None or not note.strip() else note
        if normalized is not None:
            _encode_note(normalized)
        with self._lock:
            contents = self._load()
            key = (rule_id, identity)
            existing = contents.findings.get(key)
            if existing is None and len(contents.findings) >= MAX_FINDINGS:
                raise AdvisorViolationError(409, "Too many dismissed findings: restore some before dismissing more.")
            updated = DismissedFinding(rule_id, identity, normalized)
            if updated != existing:
                contents.findings[key] = updated
                self._save(contents)
            return contents.view()

    def restore_finding(self, rule_id: str, identity: str) -> Findings:
        _validate_finding(rule_id, identity)
        with self._lock:
            contents = self._load()
            if contents.findings.pop((rule_id, identity), None) is not None:
                self._save(contents)
            return contents.view()

    def dismissed_pairs(self) -> set[tuple[str, str]]:
        """Per-finding dismissals as ``(rule_id, identity)`` pairs (R1: G1G2 matches findings against them)."""
        return {(f.rule_id, f.identity) for f in self.list_findings().dismissed}

    def _lines(self) -> list[str]:
        try:
            return self._file.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []

    def _file_stamp(self) -> tuple[int, int] | None:
        try:
            st = self._file.stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def _load(self) -> _Contents:
        """A private copy of the parsed file (callers mutate it before saving)."""
        stamp = self._file_stamp()
        if stamp is None or stamp != self._stamp:
            self._stamp, self._contents = stamp, self._parse()
        cached = self._contents
        return _Contents(list(cached.rules), dict(cached.findings), list(cached.ignored), cached.had_rules_key)

    def _parse(self) -> _Contents:
        contents = _Contents()
        section: str | None = None
        for line in self._lines():
            if _is_top_level_key(line):
                key = _key_of(line)
                section = key if key in (_KEY, _FINDINGS_KEY) else None
                contents.had_rules_key |= key == _KEY
            elif section == _KEY and line.startswith(_ITEM):
                value = line[len(_ITEM) :].strip()
                if value and value not in contents.rules:
                    contents.rules.append(value)
            elif section == _FINDINGS_KEY and line.strip() and not line.startswith("#"):
                finding = _parse_finding(line)
                if finding is None:  # not a line this version writes: kept as it is, so a newer format is not lost
                    contents.ignored.append(line)
                else:
                    contents.findings.setdefault((finding.rule_id, finding.identity), finding)
        return contents

    def _save(self, contents: _Contents) -> None:
        preserved: list[str] = []
        in_section = False
        for line in self._lines():
            if line == _HEADER:
                continue
            if _is_top_level_key(line):
                in_section = _key_of(line) in (_KEY, _FINDINGS_KEY)
                if not in_section:
                    preserved.append(line)
            elif not in_section:
                preserved.append(line)
        while preserved and not preserved[-1].strip():
            preserved.pop()
        managed: list[str] = []
        if contents.rules or contents.had_rules_key:
            managed += [f"{_KEY}:", *(f"{_ITEM}{i}" for i in contents.rules)]
        if contents.findings or contents.ignored:
            managed += [f"{_FINDINGS_KEY}:", *map(_finding_line, contents.findings.values()), *contents.ignored]
        content = "".join(f"{line}\n" for line in [_HEADER, *preserved, "", *managed])
        self._file.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="sharpit", suffix=".tmp", dir=self._file.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
            os.replace(tmp, self._file)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        # cache what was written: a same-size rewrite within one mtime tick would otherwise read as unchanged
        self._stamp, self._contents = self._file_stamp(), contents


def _validate(rule_id: str) -> None:
    spec = advisor_for(rule_id) if _RULE_ID.fullmatch(rule_id) else None
    if spec is not None and spec.panel is not None:
        return
    if spec is not None:  # owned, but by an advisor with no panel whose gate covers the HTTP route
        raise BadRequest(NO_PANEL_MESSAGE.format(advisor=spec.id))
    raise BadRequest(f"Invalid rule id '{rule_id}'")


def _valid_finding(rule_id: str, identity: str) -> str | None:
    """The refusal message for a finding key, or None; never quotes the input."""
    if len(rule_id) > _MAX_FINDING_RULE_ID or not _RULE_ID.fullmatch(rule_id) or advisor_for(rule_id) is None:
        return "Dismissed finding rule id is not a valid advisor rule id."
    if not _IDENTITY.fullmatch(identity):
        return "Dismissed finding identity is not a valid finding identity."
    return None


def _validate_finding(rule_id: str, identity: str) -> None:
    message = _valid_finding(rule_id, identity)
    if message is not None:
        raise AdvisorViolationError(400, message)


def _encode_note(note: str) -> str:
    if len(note) > MAX_NOTE_LENGTH:
        raise AdvisorViolationError(400, f"Dismissed finding note must be at most {MAX_NOTE_LENGTH} characters.")
    try:
        raw = note.encode("utf-8")
    except UnicodeEncodeError:  # a lone surrogate
        raise AdvisorViolationError(400, "Dismissed finding note is not valid text.") from None
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_note(encoded: str) -> str | None:
    """The note stored as ``encoded``, or None unless it is exactly what ``_encode_note`` writes."""
    try:
        raw = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
        note = raw.decode("utf-8")
        canonical = _encode_note(note) == encoded
    except (binascii.Error, ValueError, AdvisorViolationError):
        return None
    return note if canonical and note.strip() else None


def _parse_finding(line: str) -> DismissedFinding | None:
    """The finding a stored line is, or None unless the line is exactly the format this store writes."""
    if not line.startswith(_ITEM):
        return None
    parts = line[len(_ITEM) :].split(" ")
    if not 2 <= len(parts) <= 3 or "" in parts or _valid_finding(parts[0], parts[1]) is not None:
        return None
    if len(parts) == 2:
        return DismissedFinding(parts[0], parts[1])
    note = _decode_note(parts[2][len(_NOTE_PREFIX) :]) if parts[2].startswith(_NOTE_PREFIX) else None
    return None if note is None else DismissedFinding(parts[0], parts[1], note)


def _finding_line(finding: DismissedFinding) -> str:
    note = "" if finding.note is None else f" {_NOTE_PREFIX}{_encode_note(finding.note)}"
    return f"{_ITEM}{finding.rule_id} {finding.identity}{note}"


def _is_top_level_key(line: str) -> bool:
    return bool(line.strip()) and not line[0].isspace() and line[0] not in "#-" and ":" in line


def _key_of(line: str) -> str:
    return line.partition(":")[0].strip()
