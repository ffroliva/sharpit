"""Async and I/O rules (WAVE-B §7: FAPI-ASYNC-001/002, FAPI-HTTP-001, background tasks)."""

from __future__ import annotations

from pathlib import Path

from .support import messages, run_rules

# ``requests`` is never imported: the rules read names statically and no handler body runs
SOURCE = """
import asyncio
import time
from subprocess import run as sh


async def slow_async():
    time.sleep(1)
    return {}


async def fine_async():
    await asyncio.sleep(1)
    return {}


def sync_io():
    sh(["ls"])
    return requests.get("https://example.invalid", timeout=3).text


def sync_pure(a: int, b: int) -> int:
    return a + b


def crunch(n):
    for _ in range(n):
        time.sleep(0.1)


def enqueue(background_tasks):
    background_tasks.add_task(crunch, 10)
    return {}


def call_out():
    return requests.post("https://example.invalid").text
"""
ROUTES = {
    "GET /slow": "slow_async",
    "GET /fine": "fine_async",
    "GET /io": "sync_io",
    "GET /pure": "sync_pure",
    "POST /enqueue": "enqueue",
}


def test_blocking_call_in_async_flagged(tmp_path: Path) -> None:
    found = messages(run_rules(tmp_path, SOURCE, ROUTES), "FASTAPI-ASYNC-002")
    assert len(found) == 1
    assert "GET /slow" in found[0]
    assert "time.sleep" in found[0]


def test_await_asyncio_sleep_not_flagged(tmp_path: Path) -> None:
    evaluation = run_rules(tmp_path, SOURCE, ROUTES)
    assert "FASTAPI-ASYNC-002" in evaluation.evaluated
    assert [m for m in messages(evaluation, "FASTAPI-ASYNC-002") if "GET /fine" in m] == []


def test_sync_endpoint_doing_io_flagged(tmp_path: Path) -> None:
    found = messages(run_rules(tmp_path, SOURCE, ROUTES), "FASTAPI-ASYNC-001")
    assert len([m for m in found if "GET /io" in m]) == 1
    assert "subprocess.run" in found[0]


def test_sync_endpoint_without_io_not_flagged(tmp_path: Path) -> None:
    evaluation = run_rules(tmp_path, SOURCE, ROUTES)
    assert "FASTAPI-ASYNC-001" in evaluation.evaluated
    assert [m for m in messages(evaluation, "FASTAPI-ASYNC-001") if "GET /pure" in m] == []


def test_background_task_heavy_work(tmp_path: Path) -> None:
    found = messages(run_rules(tmp_path, SOURCE, ROUTES), "FASTAPI-BG-001")
    assert len(found) == 1
    assert "crunch" in found[0]


def test_requests_without_timeout_flagged(tmp_path: Path) -> None:
    found = messages(run_rules(tmp_path, SOURCE, ROUTES), "FASTAPI-HTTP-001")
    assert len(found) == 1
    assert "requests.post" in found[0]
