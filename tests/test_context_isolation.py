"""A test that installs an app and never shuts it down must not leave a routing context for the next test.

Outside a request ``dispatch`` routes to the only live context; a leaked one makes the next test's context ambiguous,
so its statements reach no recorder (the flaky ``test_sqlite3_source_masks_positional_secrets``).
"""

from __future__ import annotations

from pathlib import Path

from examples.fastapi_sample.app import create_app

from sharpit.engine.sources import dispatch

_KEEP_ALIVE: list[object] = []  # a strong ref stands in for the reference cycles that keep a real leak alive


def _live() -> int:
    return sum(1 for ref in dispatch._refs if ref() is not None)  # pyright: ignore[reportPrivateUsage]


def test_a_installs_without_shutdown(tmp_path: Path):
    _KEEP_ALIVE.append(create_app(show_banner=False, state_dir=str(tmp_path), sql_trace_capture_parameters=True))
    assert _live() == 1


def test_b_starts_without_leaked_contexts():
    assert _live() == 0
