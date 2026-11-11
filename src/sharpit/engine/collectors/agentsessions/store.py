from __future__ import annotations

import contextlib
import logging
import os
import stat
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sharpit.engine.collectors.agentsessions import AgentSessionSettings

from sharpit.engine.collectors.agentsessions.dashboard import build_dashboard
from sharpit.engine.collectors.agentsessions.parser import Layout, ParsedSession, parse_session

logger = logging.getLogger("sharpit")  # never create a PlaceHolder under sharpit.*; see test_own_logger_refused


def resolve_dir(configured: str | None, default_sub: str) -> Path:
    if not configured or not configured.strip():
        return (Path.home() / default_sub).resolve()
    return Path(os.path.expanduser(configured.strip())).resolve()


def display_session_dir(path: Path, configured: str | None = None) -> str:
    if configured and configured.strip().startswith("~"):
        return configured.strip()
    home = Path.home().resolve()
    resolved = path.resolve()
    if resolved == home:
        return "~"
    try:
        rel = resolved.relative_to(home)
        return "~/" + rel.as_posix()
    except ValueError:
        return str(resolved)


def _in_window(timestamp: int | None, since: int | None, until: int | None) -> bool:
    if timestamp is None:
        return False
    if since is not None and timestamp < since:
        return False
    return until is None or timestamp < until


def _matches_window(ps: ParsedSession, since: int | None, until: int | None) -> bool:
    if since is None and until is None:
        return True
    if any(_in_window(b_start, since, until) for b_start in ps.activity_by_hour):
        return True
    fallback = ps.counts.get("lastActivityEpochMillis") or ps.summary.get("updatedAtEpochMillis")
    return _in_window(fallback, since, until)


def _is_confined(target: Path | os.DirEntry[str], root: Path) -> bool:
    if target.is_symlink():
        return False
    if hasattr(target, "is_junction") and target.is_junction():
        return False
    try:
        p = Path(target.path) if isinstance(target, os.DirEntry) else target
        return p.resolve().is_relative_to(root.resolve())
    except (ValueError, OSError):
        return False


def _check_candidate_file(p: Path, max_bytes: int, root: Path) -> os.stat_result | None:
    try:
        if not _is_confined(p, root):
            return None
        st = p.stat()
        if not stat.S_ISREG(st.st_mode):
            return None
        if st.st_size > max_bytes:
            logger.warning("skipping %s exceeds 32MB limit", p)
            return None
        return st
    except OSError:
        return None


def _scan_copilot_candidates(dir_path: Path, max_bytes: int) -> list[tuple[str, Path, os.stat_result, bool]]:
    candidates: list[tuple[str, Path, os.stat_result, bool]] = []
    try:
        with os.scandir(dir_path) as entries:
            for entry in entries:
                if entry.is_dir():
                    if not _is_confined(entry, dir_path):
                        continue
                    ev = Path(entry.path) / "events.jsonl"
                    st = _check_candidate_file(ev, max_bytes, dir_path)
                    if st is not None:
                        candidates.append((entry.name, ev, st, True))
                elif entry.name.lower().endswith(".json"):
                    p = Path(entry.path)
                    st = _check_candidate_file(p, max_bytes, dir_path)
                    if st is not None:
                        candidates.append((p.stem, p, st, False))
    except OSError:
        pass
    return candidates


def _scan_claude_subdir(entry_path: str, max_bytes: int, root: Path) -> list[tuple[str, Path, os.stat_result, bool]]:
    candidates: list[tuple[str, Path, os.stat_result, bool]] = []
    try:
        with os.scandir(entry_path) as sub_entries:
            for sub in sub_entries:
                if sub.name.lower().endswith(".jsonl"):
                    sub_p = Path(sub.path)
                    st = _check_candidate_file(sub_p, max_bytes, root)
                    if st is not None:
                        candidates.append((sub_p.stem, sub_p, st, True))
    except OSError:
        pass
    return candidates


def _scan_claude_candidates(dir_path: Path, max_bytes: int) -> list[tuple[str, Path, os.stat_result, bool]]:
    candidates: list[tuple[str, Path, os.stat_result, bool]] = []
    try:
        with os.scandir(dir_path) as entries:
            for entry in entries:
                if entry.is_dir():
                    if not _is_confined(entry, dir_path):
                        continue
                    candidates.extend(_scan_claude_subdir(entry.path, max_bytes, dir_path))
                elif entry.name.lower().endswith(".jsonl"):
                    p = Path(entry.path)
                    st = _check_candidate_file(p, max_bytes, dir_path)
                    if st is not None:
                        candidates.append((p.stem, p, st, True))
    except OSError:
        pass
    return candidates


class SessionStore:
    def __init__(self, settings: AgentSessionSettings, layout: Layout, clock: Any = None) -> None:
        self.settings = settings
        self.layout = layout
        self.clock = clock
        self._lock = threading.Lock()
        default_sub = ".copilot/session-state" if layout == Layout.COPILOT else ".claude/projects"
        self._default_dir_str = f"~/{default_sub}"
        self._source_name = "Copilot CLI" if layout == Layout.COPILOT else "Claude Code"
        self._panel_title = "Copilot" if layout == Layout.COPILOT else "Claude Code"
        self.dir_path = resolve_dir(settings.session_state_dir, default_sub)
        self.display_dir = display_session_dir(self.dir_path, settings.session_state_dir)
        self._sessions: dict[str, ParsedSession] = {}
        self._available_session_file_count: int = 0
        self._selected_session_file_count: int = 0

    def is_directory_available(self) -> bool:
        return self.dir_path.exists() and self.dir_path.is_dir()

    def is_available(self) -> bool:
        if (self.settings.enabled or "").upper() == "OFF":
            return False
        return self.is_directory_available()

    def refresh(self) -> int:
        with self._lock:
            if not self.is_available():
                self._sessions.clear()
                self._available_session_file_count = 0
                self._selected_session_file_count = 0
                return 0

            max_bytes = 32 * 1024 * 1024
            if self.layout == Layout.COPILOT:
                candidates = _scan_copilot_candidates(self.dir_path, max_bytes)
            else:
                candidates = _scan_claude_candidates(self.dir_path, max_bytes)

            # Sort descending by mtime, then id, then file path
            candidates.sort(key=lambda c: (-c[2].st_mtime_ns, c[0], str(c[1])))
            max_parsed = min(max(1, self.settings.max_parsed_sessions), 1000)
            selected = candidates[:max_parsed]
            self._available_session_file_count = len(candidates)
            self._selected_session_file_count = len(selected)

            seen_ids: set[str] = set()
            for sess_id, file_path, st, _is_jsonl in selected:
                seen_ids.add(sess_id)
                mtime_ms = int(st.st_mtime * 1000)
                existing = self._sessions.get(sess_id)
                if existing is not None and existing.file_size == st.st_size and existing.file_mtime == mtime_ms:
                    continue
                parsed = parse_session(file_path, self.settings.max_events_per_session, include_lifecycle=True)
                with contextlib.suppress(Exception):
                    parsed.summary["filename"] = str(file_path.relative_to(self.dir_path)).replace("\\", "/")
                self._sessions[sess_id] = parsed

            # Prune removed or out-of-cap sessions
            for k in self._sessions.keys() - seen_ids:
                del self._sessions[k]

            return len(self._sessions)

    def _cap_warning(self) -> str | None:
        if self._available_session_file_count > self._selected_session_file_count:
            return (
                f"Loaded the {self._selected_session_file_count} most recently modified "
                f"{self._panel_title} session files out of {self._available_session_file_count}; "
                f"increase SHARPIT_{self._panel_title.upper()}_MAX_PARSED_SESSIONS to inspect older sessions."
            )
        return None

    def unavailable_reason(self) -> str:
        if (self.settings.enabled or "").upper() == "OFF":
            return f"{self._panel_title} panel is disabled via configuration"
        return f"{self._source_name} session directory not found at {self.display_dir}"

    def _unavailable_reason(self) -> str:
        return self.unavailable_reason()

    def sessions(self, since: int | None = None, until: int | None = None, *, refresh: bool = True) -> dict[str, Any]:
        if refresh:
            self.refresh()
        max_s = min(max(1, self.settings.max_sessions), 1000)
        if not self.is_available():
            return {
                "available": False,
                "unavailableReason": self._unavailable_reason(),
                "sessionStateDir": self.display_dir,
                "total": 0,
                "returned": 0,
                "maxSessions": self.settings.max_sessions,
                "sessions": [],
                "warnings": [],
            }

        with self._lock:
            sessions_snapshot = list(self._sessions.values())

        matching = [ps for ps in sessions_snapshot if _matches_window(ps, since, until)]
        sorted_sessions = sorted(
            matching,
            key=lambda s: (
                s.summary.get("updatedAtEpochMillis") or 0,
                s.summary.get("startedAtEpochMillis") or 0,
                s.summary.get("id") or "",
            ),
            reverse=True,
        )
        limited = sorted_sessions[:max_s]
        summaries = [s.summary for s in limited]
        warnings = self._sessions_warnings(len(sorted_sessions), summaries)

        return {
            "available": True,
            "unavailableReason": None,
            "sessionStateDir": self.display_dir,
            "total": len(sorted_sessions),
            "returned": len(summaries),
            "maxSessions": self.settings.max_sessions,
            "sessions": summaries,
            "warnings": warnings,
        }

    def _sessions_warnings(self, total: int, summaries: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        cap_w = self._cap_warning()
        if cap_w:
            warnings.append(cap_w)
        if total > len(summaries):
            warnings.append(f"Showing the {len(summaries)} most recent {self._panel_title} sessions out of {total}.")
        if any(s.get("schemaDrift") for s in summaries):
            warnings.append(
                f"One or more sessions did not match the expected {self._source_name} schema; "
                "some details may be missing."
            )
        return warnings

    def dashboard(self, *, refresh: bool = True) -> dict[str, Any]:
        if refresh:
            self.refresh()
        if not self.is_available():
            return build_dashboard(
                [],
                False,
                self._unavailable_reason(),
                self.display_dir,
                panel_title=self._panel_title,
            )
        warnings: list[str] = []
        cap_w = self._cap_warning()
        if cap_w:
            warnings.append(cap_w)
        clock_val = self.clock() if callable(self.clock) else self.clock
        clock_ms: int | None = int(clock_val) if isinstance(clock_val, (int, float)) else None
        with self._lock:
            sessions_snapshot = list(self._sessions.values())
        return build_dashboard(
            sessions_snapshot,
            True,
            None,
            self.display_dir,
            warnings=warnings,
            clock_millis=clock_ms,
            panel_title=self._panel_title,
        )

    def detail(self, session_id: str) -> dict[str, Any] | None:
        self.refresh()
        if not self.is_available():
            return None
        with self._lock:
            ps = self._sessions.get(session_id)
        if ps is None:
            return None
        returned = min(len(ps.events), 200)
        recent = ps.events[-returned:] if returned > 0 else []
        warnings: list[str] = []
        if ps.summary.get("schemaDrift"):
            warnings.append(
                f"Session did not match the expected {self._source_name} schema; some details may be missing."
            )
        err_cnt = ps.summary.get("errorCount", 0)
        if err_cnt > len(ps.failure_events):
            warnings.append(f"Showing {len(ps.failure_events)} retained failures out of {err_cnt} total failures.")
        return {
            "summary": ps.summary,
            "counts": ps.counts,
            "turns": ps.turns,
            "recentEvents": recent,
            "failureEvents": ps.failure_events,
            "warnings": warnings,
        }

    def events(
        self,
        session_id: str,
        category: str | None = None,
        since: int | None = None,
        limit: int = 200,
    ) -> dict[str, Any] | None:
        self.refresh()
        if not self.is_available():
            return None
        with self._lock:
            ps = self._sessions.get(session_id)
        if ps is None:
            return None
        evs = ps.events
        if category and category.strip():
            cat_norm = category.strip().upper()
            evs = [e for e in evs if e.get("category") == cat_norm]
        if since is not None:
            evs = [e for e in evs if e.get("timestampEpochMillis") is not None and e["timestampEpochMillis"] >= since]
        total = len(evs)
        bounded = min(len(evs), max(1, limit))
        ret = evs[-bounded:] if bounded > 0 else []
        return {
            "sessionId": session_id,
            "total": total,
            "returned": len(ret),
            "events": ret,
        }

    def raw(self, session_id: str, event_id: str) -> None:
        # The route's call signature; raw lines are never retained, so nothing can be revealed.
        del session_id, event_id
