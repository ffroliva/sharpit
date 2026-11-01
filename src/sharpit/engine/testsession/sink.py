"""The test-session sink (0.3.0 spec §6.4): receives SQL events and exceptions, attributes them to the running test.

Only counts and masked, normalised text are kept: bound parameters are dropped on arrival, and no gate reads a
duration (spec §6.4, B4 and B8).
"""

from __future__ import annotations

import hashlib
import re
import threading
import weakref
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from sharpit.engine.capture.exceptions import fingerprint
from sharpit.engine.capture.sqltrace import category_of, normalize
from sharpit.engine.masking import Masker
from sharpit.engine.sources.dispatch import SqlEvent, TestTag
from sharpit.engine.spi import ApiModel
from sharpit.engine.testsession.facts import PHASES, PhaseFacts, SessionFacts, TestFacts, TestKey
from sharpit.engine.testsession.filters import filtered_rule
from sharpit.settings import SharpitSettings

MAX_UNATTRIBUTED_STATEMENTS = 500  # distinct masked statements kept for the top list; the count stays exact
_MASKING_OFF = ("false", "0", "no", "off")
_PUNCTUATION = re.compile(r"\s*([=<>!,()])\s*")


def report_masker() -> Masker:
    """The masker every report string goes through: default policy, whatever the environment says."""
    defaults = SharpitSettings()
    return Masker(defaults.expose_values, defaults.mask_secrets)


def report_masker_warnings(environ: Mapping[str, str]) -> list[str]:
    """Why the report ignored the console's settings, when the environment asks for something looser."""
    warnings: list[str] = []
    if environ.get("SHARPIT_EXPOSE_VALUES", "").strip().upper() == "FULL":
        warnings.append("report ignores SHARPIT_EXPOSE_VALUES=FULL")
    if environ.get("SHARPIT_MASK_SECRETS", "").strip().lower() in _MASKING_OFF:
        warnings.append("report ignores SHARPIT_MASK_SECRETS=false")
    return warnings


def _group_key(fingerprint_text: str) -> str:
    """The activity fingerprint with its spacing folded, so ``id=?`` and ``id = ?`` are one N+1 group."""
    return _PUNCTUATION.sub(r"\1", " ".join(fingerprint_text.split()))


@dataclass
class _Registration:
    ref: weakref.ref[object]
    snapshot: tuple[str, ApiModel] | None = None  # (title, model), the latest one taken


class TestSessionSink:
    __test__ = False  # not a pytest test class

    def __init__(self, worker: str, masker: Masker | None = None) -> None:
        self.facts = SessionFacts(worker)
        self.current_test: TestFacts | None = None  # the test last begun (its window is open until ``end_test``)
        self._masker = masker or report_masker()
        self._lock = threading.Lock()
        self._attempts: Counter[str] = Counter()
        self._window: tuple[str, int] | None = None
        self._seen: dict[int, tuple[BaseException, str, str]] = {}  # id -> (strong ref, phase, group)
        self._escaped: dict[int, BaseException] = {}
        self._group_refs: Counter[tuple[str, str]] = Counter()
        self._unattributed_by_key: dict[str, str] = {}  # group key -> masked statement
        self._registrations: list[_Registration] = []

    def _mask(self, text: str) -> str:
        return self._masker.mask_text(text) or ""

    def _failed(self, exc: BaseException) -> None:
        """A broken hook costs a missing fact and one warning, never the host's query or the session."""
        warning = f"a sharpit session hook failed ({type(exc).__name__}); some facts may be missing"
        if warning not in self.facts.warnings:
            self.facts.warnings.append(warning)

    def begin_test(self, node_id: str) -> int:
        with self._lock:
            self._attempts[node_id] += 1
            attempt = self._attempts[node_id]
            self.current_test = TestFacts(TestKey(node_id, self.facts.worker, attempt))
            self.facts.tests.append(self.current_test)
            self._window = (node_id, attempt)
            self._seen.clear()
            self._escaped.clear()
            self._group_refs.clear()
            return attempt

    def end_test(self) -> None:
        with self._lock:
            self._window = None
            self._seen.clear()
            self._escaped.clear()

    def _phase_of(self, test: TestTag | None) -> PhaseFacts | None:
        """The phase a tagged event counts against: only the running test's own attempt, else None (unattributed)."""
        window, current = self._window, self.current_test
        if test is None or window is None or current is None:
            return None
        if test[0] != window[0] or test[1] != window[1] or test[2] not in PHASES:
            return None
        return current.phases.setdefault(test[2], PhaseFacts())

    def on_sql(self, event: SqlEvent, test: TestTag | None) -> None:
        try:
            rule = filtered_rule(event.sql)
            normalized = None if rule else normalize(event.sql)
            with self._lock:
                phase = self._phase_of(test)
                if normalized is None:
                    self.facts.filtered += 1
                    if phase is not None:
                        phase.filtered += 1
                    return
                key = _group_key(normalized.fingerprint)
                if phase is None:
                    self._count_unattributed(key, normalized.sql)
                    return
                phase.queries += 1
                if category_of(event.sql) == "SELECT":
                    phase.selects[key] += 1
                    if key not in phase.sql_of:
                        phase.sql_of[key] = self._mask(normalized.sql)
        except Exception as exc:  # noqa: BLE001
            self._failed(exc)

    def _count_unattributed(self, key: str, sql: str) -> None:
        self.facts.unattributed += 1
        top = self.facts.top_unattributed
        masked = self._unattributed_by_key.get(key)
        if masked is None:
            if len(self._unattributed_by_key) >= MAX_UNATTRIBUTED_STATEMENTS:
                return
            masked = self._unattributed_by_key[key] = self._mask(sql)
        top[masked] = top.get(masked, 0) + 1

    def on_exception(self, exc: BaseException, source: str, test: TestTag | None) -> None:
        del source  # every source shares the one de-duplication by object
        try:
            with self._lock:
                phase = self._phase_of(test)
                if phase is None or test is None:
                    self.facts.unattributed_exceptions += 1
                    return
                identity = id(exc)
                if identity in self._seen or identity in self._escaped:
                    return
                group = fingerprint(exc)
                phase.exceptions += 1
                phase.exception_groups.setdefault(group, (type(exc).__name__, self._mask(str(exc))))
                self._seen[identity] = (exc, test[2], group)
                self._group_refs[test[2], group] += 1
        except Exception as error:  # noqa: BLE001
            self._failed(error)

    def on_escaped(self, exc: BaseException) -> None:
        try:
            with self._lock:
                identity = id(exc)
                self._escaped[identity] = exc
                counted = self._seen.pop(identity, None)
                if counted is None or self.current_test is None:
                    return
                _, phase_name, group = counted
                phase = self.current_test.phases[phase_name]
                phase.exceptions -= 1
                self._group_refs[phase_name, group] -= 1
                if self._group_refs[phase_name, group] <= 0:
                    phase.exception_groups.pop(group, None)
        except Exception as error:  # noqa: BLE001
            self._failed(error)

    def register_app(self, app: object) -> None:
        try:
            with self._lock:
                self._registrations.append(_Registration(weakref.ref(app)))
        except Exception as exc:  # noqa: BLE001
            self._failed(exc)

    def snapshot_apps(self, model_of: Callable[[object], ApiModel]) -> None:
        """Take the model of every registered app that is still alive; the latest snapshot per registration is kept."""
        with self._lock:
            registrations = list(self._registrations)
        for registration in registrations:
            app = registration.ref()
            if app is None:
                continue
            try:
                title = self._mask(str(getattr(app, "title", type(app).__name__)))
                registration.snapshot = (title, model_of(app))
            except Exception as exc:  # noqa: BLE001
                self._failed(exc)

    def app_snapshots(self) -> list[tuple[str, ApiModel]]:
        """``(identity, model)`` per distinct content, identity ``"<title>#<8 hex of sha256 of the model>"``."""
        found: dict[str, ApiModel] = {}
        with self._lock:
            snapshots = [r.snapshot for r in self._registrations if r.snapshot is not None]
        for title, model in snapshots:
            digest = hashlib.sha256(repr(model).encode("utf-8")).hexdigest()[:8]
            found.setdefault(f"{title}#{digest}", model)
        return list(found.items())
