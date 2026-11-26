"""W6 S3 budgets, by event count: what the resident audit hook and each sensor add per audit event.

The real hook cannot be removed, so the resident hook is measured by calling ``hub._dispatch`` against an empty hook,
the two alternating round by round (a drifting machine slows both alike), and the sensors by subscribing and
unsubscribing between interleaved rounds. All of it runs in one child interpreter that prints its rounds; this process
turns them into ``paired`` results. See docs/development/overhead-budgets.md.
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
RESIDENT_HOOK_BUDGET = 1.0e-6  # us/event the dispatcher adds over an empty hook: one dict lookup that finds nothing
PROCESSES_SENSOR_BUDGET = 6.0e-6  # us/event: minimise + offer, against the flag test
# us/event on a hot set of 64 files (the sensor remembers 256 paths): lookup + offer. A path it has not seen costs about
# 11 us once (pattern, mask, collapse); that is not budgeted here, it is paid per new file beside the open() itself.
FILES_SENSOR_BUDGET = 6.0e-6

CHILD = """
import json, os, sys, time
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sensors.audit import AuditHub
from sharpit.engine.sensors.files import FilesSensor
from sharpit.engine.sensors.processes import ProcessesSensor

EVENTS, ROUNDS = @EVENTS@, @ROUNDS@
journal = RuntimeJournal(sources=["processes", "files"], max_events=EVENTS * ROUNDS * 8)
processes, files, hub = ProcessesSensor(), FilesSensor(Masker(Exposure.MASKED, True).mask_path), AuditHub()
hub.enable(processes, journal)  # installs the real hook once; both sides of a sensor round then pay for it alike
hub.disable(processes)
unsubscribed = ("sharpit.budget.unsubscribed", (1,))

lib_file = os.path.join(sys.prefix, "Lib", "site-packages", "_sharpit_budget_lib.py")
lib_ns = {"__name__": "_sharpit_budget_lib"}
exec(
    compile(
        "def deep_lib(n, fn):\\n    return fn() if n <= 0 else deep_lib(n - 1, fn)\\n",
        lib_file,
        "exec",
    ),
    lib_ns,
)
deep_lib = lib_ns["deep_lib"]

app_file = os.path.abspath("_sharpit_budget_app.py")
app_ns = {"__name__": "_sharpit_budget_app"}
exec(compile("def app_top(fn):\\n    return fn()\\n", app_file, "exec"), app_ns)
app_top = app_ns["app_top"]

def empty(event, args):
    return None

def direct(call, event, args):
    start = time.perf_counter()
    for _ in range(EVENTS):
        call(event, args)
    return (time.perf_counter() - start) / EVENTS

def audited(event, *args):
    audit = sys.audit
    start = time.perf_counter()
    for _ in range(EVENTS):
        audit(event, *args)
    return (time.perf_counter() - start) / EVENTS

popen = lambda: deep_lib(64, lambda: audited("subprocess.Popen", "/usr/bin/git", ["git", "status"], None, None))
HOT = [f"reports/report-{i}/data.csv" for i in range(64)]  # a hot set of distinct files, each opened over and over

def opened():
    audit, hot = sys.audit, HOT
    start = time.perf_counter()
    for i in range(EVENTS):
        audit("open", hot[i & 63], "r", 0)
    return (time.perf_counter() - start) / EVENTS

def reset_files():
    files._seen.clear()
    patterns = getattr(files, "_patterns", None)
    if patterns is not None:
        patterns.clear()

def alternate(first, second):
    one, two = [], []
    for i in range(ROUNDS):
        for side in ((0, 1) if i % 2 == 0 else (1, 0)):
            (one, two)[side].append((first, second)[side]())
    return one, two

def switched(sensor, round_, before_on=None):
    def run(on):
        if on:
            if before_on is not None:
                before_on()
            hub.enable(sensor, journal)
        out = round_()
        hub.disable(sensor)
        return out
    return run

def measure_rounds(sensor, round_, before_on=None):
    off, on = [], []
    step = switched(sensor, round_, before_on)
    for i in range(ROUNDS):
        for side in (("off", "on") if i % 2 == 0 else ("on", "off")):
            (on if side == "on" else off).append(step(side == "on"))
    return off, on

resident_off, resident_on = alternate(
    lambda: direct(empty, *unsubscribed), lambda: direct(hub._dispatch, *unsubscribed)
)
off, on = measure_rounds(processes, popen)
files_no_app_off, files_no_app_on = measure_rounds(files, lambda: deep_lib(64, opened), reset_files)
files_app_off, files_app_on = measure_rounds(files, lambda: deep_lib(64, lambda: app_top(opened)), reset_files)
files_off, files_on = measure_rounds(files, opened)
print(json.dumps({
    "resident_off": resident_off, "resident_on": resident_on, "off": off, "on": on,
    "files_no_app_off": files_no_app_off, "files_no_app_on": files_no_app_on,
    "files_app_off": files_app_off, "files_app_on": files_app_on,
    "files_off": files_off, "files_on": files_on, "recorded": journal.status()["recorded"],
}))
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
    # one row per subscribed event, none for the rest
    assert measured["recorded"] == {"processes": EVENTS * ROUNDS, "files": EVENTS * ROUNDS * 3}
    resident = _result(measured["resident_off"], measured["resident_on"])
    check_budget("resident audit hook", resident, RESIDENT_HOOK_BUDGET, "us/event", 1e-6)
    sensor = _result(measured["off"], measured["on"])
    check_budget("processes sensor", sensor, PROCESSES_SENSOR_BUDGET, "us/event", 1e-6)
    check_budget(
        "files sensor (new pattern, 64 frames, no app frame)",
        _result(measured["files_no_app_off"], measured["files_no_app_on"]),
        FILES_SENSOR_BUDGET,
        "us/event",
        1e-6,
    )
    check_budget(
        "files sensor (new pattern, app frame near top)",
        _result(measured["files_app_off"], measured["files_app_on"]),
        FILES_SENSOR_BUDGET,
        "us/event",
        1e-6,
    )
    check_budget(
        "files sensor (_seen hit)",
        _result(measured["files_off"], measured["files_on"]),
        FILES_SENSOR_BUDGET,
        "us/event",
        1e-6,
    )
