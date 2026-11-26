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
import json, sys, time
from sharpit.engine.capture.correlation import REQUEST, RequestInfo
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sensors.audit import AuditHub
from sharpit.engine.sensors.files import FilesSensor
from sharpit.engine.sensors.processes import ProcessesSensor
from sharpit.engine.sensors.sinks import SinkMatcher

EVENTS, ROUNDS = @EVENTS@, @ROUNDS@
mask_path = Masker(Exposure.MASKED, True).mask_path
journal = RuntimeJournal(sources=["processes", "files"], max_events=EVENTS * ROUNDS * 12)
matcher_off = SinkMatcher("ctx", lambda: False)
matcher_on = SinkMatcher("ctx", lambda: True)
processes = ProcessesSensor(context_id="ctx")
processes_matcher_off = ProcessesSensor(matcher=matcher_off)
files = FilesSensor(mask_path, context_id="ctx")
files_matcher_off = FilesSensor(mask_path, matcher=matcher_off)
files_matcher_on = FilesSensor(mask_path, matcher=matcher_on)
hub = AuditHub()
hub.enable(processes, journal)  # installs the real hook once; both sides of a sensor round then pay for it alike
hub.disable(processes)
unsubscribed = ("sharpit.budget.unsubscribed", (1,))
request = RequestInfo("a" * 16, "ctx", "GET", "/", None, 0, None)

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

popen = lambda: audited("subprocess.Popen", "/usr/bin/git", ["git", "status"], None, None)

def popen_with_request():
    token = REQUEST.set(request)
    try:
        return popen()
    finally:
        REQUEST.reset(token)

HOT = [f"reports/report-{i}/data.csv" for i in range(64)]  # a hot set of distinct files, each opened over and over

def opened():
    audit, hot = sys.audit, HOT
    start = time.perf_counter()
    for i in range(EVENTS):
        audit("open", hot[i & 63], "r", 0)
    return (time.perf_counter() - start) / EVENTS

def reset_files():
    files._seen.clear()

# 64 paths exceed the 32-hash miss ring; 10 requests x 200 events stay under MAX_CHECKS and clear() resets rounds.
def requests_for(query):
    scope = {"query_string": query, "path_params": {}}
    return [RequestInfo(f"{r:016x}", "ctx", "GET", "/", None, 0, None, scope=scope) for r in range(10)]

requests_one = requests_for(b"q=unmatchedval")
requests_many = requests_for("&".join(f"q{i}=unmatched{i:03d}" for i in range(32)).encode())

def opened_with(requests):
    def run():
        audit, hot = sys.audit, HOT
        i = 0
        start = time.perf_counter()
        for req in requests:
            token = REQUEST.set(req)
            try:
                for _ in range(200):
                    audit("open", hot[i & 63], "r", 0)
                    i += 1
            finally:
                REQUEST.reset(token)
        return (time.perf_counter() - start) / EVENTS
    return run

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
req_off, req_on = measure_rounds(processes, popen_with_request)
proc_matcher_off, proc_matcher_on = measure_rounds(processes_matcher_off, popen)
files_new_off, files_new_on = measure_rounds(files, opened, reset_files)
files_off, files_on = measure_rounds(files, opened)
files_m_off_off, files_m_off_on = measure_rounds(files_matcher_off, opened)
files_no_req_off, files_no_req_on = measure_rounds(files_matcher_on, opened)
files_one_off, files_one_on = measure_rounds(files_matcher_on, opened_with(requests_one), matcher_on.clear)
files_many_off, files_many_on = measure_rounds(files_matcher_on, opened_with(requests_many), matcher_on.clear)
print(json.dumps({
    "resident_off": resident_off, "resident_on": resident_on, "off": off, "on": on,
    "req_off": req_off, "req_on": req_on,
    "proc_matcher_off": proc_matcher_off, "proc_matcher_on": proc_matcher_on,
    "files_new_off": files_new_off, "files_new_on": files_new_on,
    "files_off": files_off, "files_on": files_on,
    "files_m_off_off": files_m_off_off, "files_m_off_on": files_m_off_on,
    "files_no_req_off": files_no_req_off, "files_no_req_on": files_no_req_on,
    "files_one_off": files_one_off, "files_one_on": files_one_on,
    "files_many_off": files_many_off, "files_many_on": files_many_on,
    "recorded": journal.status()["recorded"],
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
    assert measured["recorded"] == {"processes": EVENTS * ROUNDS * 3, "files": EVENTS * ROUNDS * 6}
    resident = _result(measured["resident_off"], measured["resident_on"])
    check_budget("resident audit hook", resident, RESIDENT_HOOK_BUDGET, "us/event", 1e-6)
    sensor = _result(measured["off"], measured["on"])
    check_budget("processes sensor", sensor, PROCESSES_SENSOR_BUDGET, "us/event", 1e-6)
    check_budget(
        "processes sensor (with request id)",
        _result(measured["req_off"], measured["req_on"]),
        PROCESSES_SENSOR_BUDGET,
        "us/event",
        1e-6,
    )
    check_budget(
        "processes sensor (matcher off)",
        _result(measured["proc_matcher_off"], measured["proc_matcher_on"]),
        PROCESSES_SENSOR_BUDGET,
        "us/event",
        1e-6,
    )
    check_budget(
        "files sensor (new pattern)",
        _result(measured["files_new_off"], measured["files_new_on"]),
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
    check_budget(
        "files sensor (matcher off)",
        _result(measured["files_m_off_off"], measured["files_m_off_on"]),
        FILES_SENSOR_BUDGET,
        "us/event",
        1e-6,
    )
    check_budget(
        "files sensor (matcher on, no request)",
        _result(measured["files_no_req_off"], measured["files_no_req_on"]),
        FILES_SENSOR_BUDGET,
        "us/event",
        1e-6,
    )
    check_budget(
        "files sensor (matcher on, 1 value)",
        _result(measured["files_one_off"], measured["files_one_on"]),
        FILES_SENSOR_BUDGET,
        "us/event",
        1e-6,
    )
    check_budget(
        "files sensor (matcher on, 32 values)",
        _result(measured["files_many_off"], measured["files_many_on"]),
        FILES_SENSOR_BUDGET,
        "us/event",
        1e-6,
    )
