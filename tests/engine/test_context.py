import threading
from typing import Any

from sharpit.engine.activation import ActivationStatus
from sharpit.engine.context import SharpitContext
from sharpit.settings import SharpitSettings


def _ctx() -> SharpitContext:
    return SharpitContext(SharpitSettings(), ActivationStatus(True, True, "test", ()), None)  # pyright: ignore[reportArgumentType]


def test_lazy_keys_do_not_wait_for_each_other():
    ctx = _ctx()
    started, release = threading.Event(), threading.Event()

    def slow() -> str:
        started.set()
        release.wait(10)
        return "slow"

    worker = threading.Thread(target=ctx.lazy, args=("slow", slow))
    worker.start()
    assert started.wait(5)
    other: dict[str, Any] = {}
    probe = threading.Thread(target=lambda: other.setdefault("fast", ctx.lazy("fast", lambda: "fast")))
    probe.start()
    probe.join(3)
    blocked = probe.is_alive()
    release.set()
    worker.join(10)
    probe.join(10)
    assert not blocked
    assert other == {"fast": "fast"}
    assert ctx.lazy("slow", lambda: "again") == "slow"


def test_lazy_factory_runs_once_per_key_under_concurrency():
    ctx = _ctx()
    calls: list[int] = []
    gate = threading.Barrier(8)

    def factory() -> int:
        calls.append(1)
        return len(calls)

    def call() -> None:
        gate.wait(5)
        ctx.lazy("k", factory)

    threads = [threading.Thread(target=call) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert calls == [1]


def test_lazy_is_reentrant_across_keys():
    ctx = _ctx()
    assert ctx.lazy("outer", lambda: ctx.lazy("inner", lambda: 1) + 1) == 2
