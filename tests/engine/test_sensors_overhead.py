"""W6 S3 budgets, by event count: what the resident audit hook and the processes sensor add per audit event.

The real hook cannot be removed, so both measurements run in one child interpreter that prints its rounds; this
process turns them into ``paired`` results. See docs/development/overhead-budgets.md.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from typing import Any

from tests.overhead import check_budget, paired

EVENTS = 2_000  # audit events per round
ROUNDS = 15
RESIDENT_HOOK_BUDGET = 1.0e-6  # measured 0.44-0.62 us/event, noise <= 0.32 (Windows, py3.13, 3 runs, 2026-11-12)
PROCESSES_SENSOR_BUDGET = 6.0e-6  # measured 3.2-4.3 us/event, noise <= 0.75: minimise + offer, against the flag test

CHILD = """
import json, sys, time
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.sensors.audit import AuditHub
from sharpit.engine.sensors.processes import ProcessesSensor

EVENTS, ROUNDS = @EVENTS@, @ROUNDS@
journal = RuntimeJournal(sources=["processes"], max_events=EVENTS * ROUNDS * 2)
sensor, hub = ProcessesSensor(), AuditHub()

def timed(event, *args):
    audit = sys.audit
    start = time.perf_counter()
    for _ in range(EVENTS):
        audit(event, *args)
    return (time.perf_counter() - start) / EVENTS

other = lambda: timed("sharpit.budget.unsubscribed", 1)
popen = lambda: timed("subprocess.Popen", "/usr/bin/git", ["git", "status"], None, None)
before = [other() for _ in range(ROUNDS)]  # no hook installed yet
hub.enable(sensor, journal)
after = [other() for _ in range(ROUNDS)]  # the resident hook, nothing subscribed to the event
hub.disable(sensor)
off, on = [], []
for i in range(ROUNDS):
    for side in (("off", "on") if i % 2 == 0 else ("on", "off")):
        if side == "on":
            hub.enable(sensor, journal)
            on.append(popen())
            hub.disable(sensor)
        else:
            off.append(popen())
print(json.dumps({"before": before, "after": after, "off": off, "on": on, "recorded": journal.status()["recorded"]}))
""".replace("@EVENTS@", str(EVENTS)).replace("@ROUNDS@", str(ROUNDS))


def _measure() -> dict[str, Any]:
    done = subprocess.run(
        [sys.executable, "-I", "-c", textwrap.dedent(CHILD)], capture_output=True, text=True, timeout=300, check=False
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def _result(off: list[float], on: list[float]) -> Any:
    rounds_off, rounds_on = iter(off), iter(on)
    return paired(lambda: next(rounds_off), lambda: next(rounds_on), ROUNDS)


def test_the_sensors_overhead_budgets_by_event_count() -> None:
    measured = _measure()
    assert measured["recorded"] == {"processes": EVENTS * ROUNDS}  # one row per subscribed event, none for the rest
    resident = _result(measured["before"], measured["after"])
    sensor = _result(measured["off"], measured["on"])
    check_budget("resident audit hook", resident, RESIDENT_HOOK_BUDGET, "us/event", 1e-6)
    check_budget("processes sensor", sensor, PROCESSES_SENSOR_BUDGET, "us/event", 1e-6)
