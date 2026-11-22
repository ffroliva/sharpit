"""Class-level SQLAlchemy listeners stay singular across concurrent attach and detach."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from threading import Barrier, Event, Lock
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")
pytestmark = pytest.mark.needs_sqlalchemy

from sqlalchemy.pool import Pool  # noqa: E402

from sharpit.engine.sqla.events import add_connection_listener, add_pool_listener  # noqa: E402

THREADS = 12
ROUNDS = 200


class _RegistrationProbe:
    def __init__(self, callback: Callable[..., None]) -> None:
        self.callback = callback
        self.listen_original = sa.event.listen
        self.remove_original = sa.event.remove
        self.contains_original = sa.event.contains
        self.operations: list[str] = []
        self.checked = 0
        self.widen_window = True
        self.lock = Lock()
        self.all_checked = Event()

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sa.event, "listen", self.listen)
        monkeypatch.setattr(sa.event, "remove", self.remove)
        monkeypatch.setattr(sa.event, "contains", self.contains)

    def matches(self, target: object, event: str, fn: object) -> bool:
        return target is Pool and event == "checkin" and fn is self.callback

    def listen(self, target: Any, event: str, fn: object, *args: Any, **kwargs: Any) -> None:
        self.listen_original(target, event, fn, *args, **kwargs)
        if self.matches(target, event, fn):
            self.operations.append("listen")

    def remove(self, target: Any, event: str, fn: object, *args: Any, **kwargs: Any) -> None:
        self.remove_original(target, event, fn, *args, **kwargs)
        if self.matches(target, event, fn):
            self.operations.append("remove")

    def contains(self, target: Any, event: str, fn: object) -> bool:
        if self.matches(target, event, fn) and self.widen_window:
            with self.lock:
                self.checked += 1
                if self.checked == THREADS:
                    self.all_checked.set()
            if self.all_checked.wait(0.1):
                return False
            self.widen_window = False
        return self.contains_original(target, event, fn)


def _attach(_index: int, *, barrier: Barrier, callback: Callable[..., None]) -> Callable[[], None] | None:
    barrier.wait()
    return add_pool_listener("checkin", callback)


def _race_attach_and_detach(
    index: int,
    *,
    barrier: Barrier,
    seed_remover: Callable[[], None] | None,
    callback: Callable[..., None],
) -> Callable[[], None] | None:
    barrier.wait()
    if index % 2:
        assert seed_remover is not None
        seed_remover()
        return None
    return add_pool_listener("checkin", callback)


def test_concurrent_pool_listener_attach_registers_once(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = sa.create_engine("sqlite://")
    calls: list[None] = []

    def on_checkin(*_args: object) -> None:
        calls.append(None)

    probe = _RegistrationProbe(on_checkin)
    probe.install(monkeypatch)

    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        for _ in range(ROUNDS):
            barrier = Barrier(THREADS)
            attach = partial(_attach, barrier=barrier, callback=on_checkin)
            removers = list(executor.map(attach, range(THREADS)))
            with engine.connect():
                pass
            assert len(calls) == 1
            calls.clear()

            detach_barrier = Barrier(THREADS)
            race = partial(
                _race_attach_and_detach,
                barrier=detach_barrier,
                seed_remover=removers[0],
                callback=on_checkin,
            )
            probe.operations.clear()
            racing_removers = list(executor.map(race, range(THREADS)))
            assert probe.operations
            expected_attached = probe.operations[-1] == "listen"
            with engine.connect():
                pass
            assert len(calls) == int(expected_attached)
            calls.clear()

            for remover in (*removers, *racing_removers):
                if remover is not None:
                    remover()
            assert not sa.event.contains(Pool, "checkin", on_checkin)

    engine.dispose()


def test_concurrent_connection_listener_attach_registers_once() -> None:
    engine = sa.create_engine("sqlite://")
    calls: list[None] = []

    def on_begin(*_args: object) -> None:
        calls.append(None)

    barrier = Barrier(THREADS)

    def attach() -> Callable[[], None] | None:
        barrier.wait()
        return add_connection_listener("begin", on_begin)

    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        removers = list(executor.map(lambda _index: attach(), range(THREADS)))
    with engine.connect() as connection:
        connection.begin()
    assert len(calls) == 1
    for remover in removers:
        if remover is not None:
            remover()
    engine.dispose()
