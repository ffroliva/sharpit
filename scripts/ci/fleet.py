"""Run the full suite across up to 5 Docker cloud sandboxes (`sbx --cloud`) and print one verdict.

Each box clones the PUSHED commit from GitHub (the repo is public: no token, no local file reaches a box), runs one
`SHARPIT_SHARD=i/n` slice with pytest-xdist and returns JUnit plus timings. CI stays the gate; this is the fast Linux
check and the fallback. Runbook: docs/development/fleet.md.

    uv run python scripts/ci/fleet.py --sha HEAD --boxes 5 --out <dir>

Exit 0 green, 1 red, 2 not runnable (unpushed sha, bad box count), 3 no verdict (no box ran: credit, quota, outage).
A box that dies, times out or returns nothing is red, never rerun.
"""

from __future__ import annotations

import argparse
import os
import re
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = "https://github.com/ffroliva/sharpit.git"
MAX_BOXES = 5  # 5 boxes x 8 vCPU = the account's 40-vCPU quota; a sixth is refused by sbx
POLL_INTERVAL = 2
NAME_PREFIX = "fleet-"
NETWORK = ("github.com", "**.githubusercontent.com", "pypi.org", "files.pythonhosted.org", "astral.sh", "**.astral.sh")
TTL_S = 30 * 60  # the box TTL below; what a box left behind is charged
DEFAULT_LEDGER_DIR = "C:/development/github/sharpit-bench/bench"
stop = threading.Event()
ledger_lock = threading.Lock()
ledger: Any = None

# Epochs and /proc/stat lines are taken in the box, so host and box clocks never mix. A full clone, not a partial one:
# a partial clone broke Kliper tests that read git history (blobs fetched lazily with the network gone).
BOX_SCRIPT = """set -u
export PATH=$HOME/.local/bin:$PATH CI=true
OUT=$HOME/out; rm -rf $OUT; mkdir -p $OUT; cd $HOME
step() { echo "$1 $(date +%s%3N) $(head -1 /proc/stat)" >> $OUT/timeline.txt; }
step start
git clone -q @REPO@ s > $OUT/clone.log 2>&1 && cd s \
  && git checkout -q @SHA@ >> $OUT/clone.log 2>&1 || echo clone-failed > $OUT/fatal
step cloned
[ -f $OUT/fatal ] || uv sync --locked --extra test -q > $OUT/prepare.log 2>&1 || echo prepare-failed > $OUT/fatal
step synced
if [ ! -f $OUT/fatal ]; then
  step tests_begin
  SHARPIT_SHARD=@IDX@/@TOTAL@ SHARPIT_OVERHEAD_LOG=$OUT/overhead.jsonl uv run pytest -q -p no:cacheprovider \
    -n @WORKERS@ --durations=15 --junitxml=$OUT/pytest.xml > $OUT/pytest.log 2>&1; echo $? > $OUT/pytest.rc
  step tests_end
@OWN@fi
tar -czf $HOME/out.tgz -C $HOME out; touch $HOME/out.done
"""


# The files tests/_shard.py leaves to CI's masking-gates job (no shard collects them): run whole, no shard set. A
# failure there turns the box's exit code red.
OWN_JOB_STEP = """  OWN=$(uv run python -c "import sys; sys.path[:0]=['tests']; import _shard; print(*_shard.OWN_JOB)")
  uv run pytest -q -p no:cacheprovider -n @WORKERS@ --junitxml=$OUT/pytest-own.xml $OWN > $OUT/pytest-own.log 2>&1 \\
    || echo $? > $OUT/pytest.rc
  step own_end
"""


@dataclass(frozen=True)
class BoxResult:
    index: int  # 1-based, the shard number
    rc: int | None = None  # pytest's exit code; None when it never ran
    tests: int = 0  # testcases in the JUnit file
    fatal: str = ""
    timeline: str = ""
    wall: float = 0.0  # host seconds, create to result copied


def box_script(index: int, total: int, workers: int, sha: str, own_job: bool = False) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError(f"not a full sha: {sha!r}")
    values = {"REPO": REPO, "SHA": sha, "IDX": str(index), "TOTAL": str(total), "WORKERS": str(workers)}
    values["OWN"] = re.sub(r"@(\w+)@", lambda m: values[m[1]], OWN_JOB_STEP) if own_job else ""
    return re.sub(r"@(\w+)@", lambda m: values.get(m[1], m[0]), BOX_SCRIPT)


def check_boxes(count: int) -> int:
    if not 1 <= count <= MAX_BOXES:
        raise ValueError(f"--boxes {count}: 1 to {MAX_BOXES} (the account's 40 vCPUs fit {MAX_BOXES} boxes of 8)")
    return count


def box_problems(result: BoxResult, total: int) -> list[str]:
    label = f"box {result.index}/{total}"
    if result.fatal:
        return [f"{label}: {result.fatal}"]
    if result.rc is None:
        return [f"{label} returned no result"]
    if result.rc != 0:
        return [f"{label} pytest exited {result.rc}"]
    return [] if result.tests > 0 else [f"{label} ran no tests"]


def verdict(results: list[BoxResult], total: int) -> tuple[bool, list[str]]:
    """Green only when all `total` boxes reported, each exited 0 and ran tests."""
    by_index = {r.index: r for r in results}
    lines: list[str] = []
    for k in range(1, total + 1):
        lines += box_problems(by_index.get(k, BoxResult(k)), total)
    return not lines, lines


def nothing_ran(results: list[BoxResult]) -> bool:
    """No box started its tests and none reported a failure of its own: credit, quota or an outage."""
    return all(r.rc is None and not r.fatal for r in results)


def exit_code(results: list[BoxResult], total: int) -> int:
    if nothing_ran(results):
        return 3
    return 0 if verdict(results, total)[0] else 1


def timeline_marks(text: str) -> dict[str, tuple[float, list[int]]]:
    """label -> (epoch seconds, /proc/stat counters), from lines `<label> <epoch ms> cpu <counters...>`."""
    marks: dict[str, tuple[float, list[int]]] = {}
    for line in text.splitlines():
        words = line.split()
        if len(words) >= 12 and words[2] == "cpu" and all(w.isdigit() for w in words[1:2] + words[3:]):
            marks[words[0]] = (int(words[1]) / 1000, [int(w) for w in words[3:]])
    return marks


def busy_seconds(a: list[int], b: list[int]) -> float:
    """CPU-seconds between two /proc/stat snapshots: user, nice, system, irq, softirq (not idle, iowait, steal)."""
    return sum(b[i] - a[i] for i in (0, 1, 2, 5, 6)) / 100


def steal_seconds(a: list[int], b: list[int]) -> float:
    return (b[7] - a[7]) / 100


def box_figures(timeline: str) -> dict[str, float] | None:
    """setup_s (start to tests_begin), test_s, cpu_test_s, cpu_total_s, steal_s; None when the tests never began."""
    marks = timeline_marks(timeline)
    if not {"start", "tests_begin", "tests_end"} <= marks.keys():
        return None
    (t0, c0), (t1, c1), (t2, c2) = marks["start"], marks["tests_begin"], marks["tests_end"]
    return {
        "setup_s": t1 - t0,
        "test_s": t2 - t1,
        "cpu_setup_s": busy_seconds(c0, c1),
        "cpu_test_s": busy_seconds(c1, c2),
        "cpu_total_s": busy_seconds(c0, c2),
        "steal_s": steal_seconds(c0, c2),
    }


def stale_boxes(ls_output: str) -> list[str]:
    """Names of `fleet-*` sandboxes in `sbx ls` output (the NAME column reads `agent/name`)."""
    names = (row.split()[0].rpartition("/")[2] for row in ls_output.splitlines()[1:] if row.split())
    return [n for n in names if n.startswith(NAME_PREFIX)]


def _sbx(*args: str, timeout: int = 300, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "GODEBUG": "tlsmlkem=0", "MSYS_NO_PATHCONV": "1"}
    return subprocess.run(
        ["sbx", "--cloud", *args], input=stdin, capture_output=True, text=True, timeout=timeout, env=env
    )


def _rm(name: str) -> bool:
    try:
        return _sbx("rm", "-f", name).returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        print(f"fleet: could not remove {name}; run `sbx --cloud rm -f {name}`", flush=True)
        return False


def sweep_stale() -> None:
    """Remove boxes a hard-killed run left behind (they bill until their TTL)."""
    try:
        listing = _sbx("ls", timeout=60)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return
    for name in stale_boxes(listing.stdout) if listing.returncode == 0 else []:
        print(f"fleet: removing stale box {name}", flush=True)
        _rm(name)


def _create(name: str) -> subprocess.CompletedProcess[str]:
    allow = [a for host in NETWORK for a in ("--allow-network", host)]
    shape = ("--cpus", "8", "--memory", "16g", "--ttl", f"{TTL_S // 60}m", "--on-timeout", "delete", "--no-progress")
    return _sbx("create", "shell", "--name", name, *shape, *allow)


def _wait_done(name: str, deadline: float) -> str:
    """'' when out.done appeared; otherwise why not."""
    while time.monotonic() < deadline:
        if stop.wait(POLL_INTERVAL):
            return "interrupted"
        try:
            if _sbx("exec", name, "test", "-f", "/home/agent/out.done", timeout=60).returncode == 0:
                return ""
        except subprocess.TimeoutExpired:
            continue
    _sbx("exec", name, "bash", "-c", "tar -czf ~/out.tgz -C ~ out", timeout=120)  # a slow box still returns its files
    return "did not finish before the deadline"


def _read(out_dir: Path, index: int, name: str, fatal: str, wall: float) -> BoxResult:
    archive, target = out_dir / f"box{index}.tgz", out_dir / f"box{index}"
    if _sbx("cp", f"{name}:/home/agent/out.tgz", str(archive)).returncode != 0:
        return BoxResult(index, fatal=fatal or "failed to copy the result", wall=wall)
    try:
        with tarfile.open(archive) as tar:
            tar.extractall(target, filter="data")
        files = target / "out"
        rc_file, xml_file, fatal_file = files / "pytest.rc", files / "pytest.xml", files / "fatal"
        rc = int(rc_file.read_text().strip() or "-1") if rc_file.exists() else None
        tests = sum(1 for _ in ET.parse(xml_file).getroot().iter("testcase")) if xml_file.exists() else 0
        fatal = fatal or (fatal_file.read_text().strip() if fatal_file.exists() else "")
        timeline = (files / "timeline.txt").read_text() if (files / "timeline.txt").exists() else ""
        return BoxResult(index, rc, tests, fatal, timeline, wall)
    except (OSError, tarfile.TarError, EOFError, ET.ParseError, ValueError) as exc:
        return BoxResult(index, fatal=fatal or f"invalid result archive: {exc}", wall=wall)


def _charge(name: str, seconds: float, removed: bool) -> None:
    """Record the box's spend in the shared ledger: measured when removed, its full TTL when it was not."""
    if ledger is None:
        return
    with ledger_lock:  # the ledger's record() is unlocked
        if removed:
            ledger.record(name, seconds, ledger.RATE_LARGE)
        else:
            ledger.record(name, TTL_S, ledger.RATE_LARGE, basis="ttl")


def load_ledger() -> object | None:
    """The machine-wide spend ledger of sharpit-bench (SBX_LEDGER_DIR), imported, never copied; None when absent."""
    folder = Path(os.environ.get("SBX_LEDGER_DIR", DEFAULT_LEDGER_DIR))
    if not (folder / "sbx_ledger.py").is_file():
        print(f"fleet: no spend ledger at {folder}; spend is not recorded", flush=True)
        return None
    sys.path.insert(0, str(folder))
    import sbx_ledger  # type: ignore[import-not-found]  # noqa: PLC0415

    return sbx_ledger


def run_box(
    index: int, total: int, sha: str, workers: int, out_dir: Path, deadline: float, own_job: bool = False
) -> BoxResult:
    name = f"{NAME_PREFIX}{sha[:9]}-{os.getpid()}-{index}of{total}"
    began = time.monotonic()
    started = time.time()
    try:
        created = _create(name)
        if created.returncode != 0:  # not a verdict on the code: exit 3 when no box gets this far
            print(f"box {index}: create failed: {created.stderr.strip()[-300:]}", flush=True)
            return BoxResult(index)
        script = out_dir / f"box{index}.sh"
        script.write_text(
            box_script(index, total, workers, sha, own_job and index == 1), encoding="utf-8", newline="\n"
        )
        if _sbx("cp", str(script), f"{name}:/home/agent/box.sh").returncode != 0:
            return BoxResult(index, fatal="failed to upload the box script")
        if _sbx("exec", name, "bash", "-c", "nohup bash ~/box.sh > ~/box.out 2>&1 & disown").returncode != 0:
            return BoxResult(index, fatal="failed to launch the box script")
        fatal = _wait_done(name, deadline)
        return _read(out_dir, index, name, fatal, time.monotonic() - began)
    except subprocess.TimeoutExpired:
        return BoxResult(index, fatal="sandbox command timed out")
    finally:
        _charge(name, time.time() - started, _rm(name))


def pushed(sha: str) -> bool:
    refs = subprocess.run(["git", "ls-remote", REPO], capture_output=True, text=True)
    return refs.returncode == 0 and any(line.split("\t")[0] == sha for line in refs.stdout.splitlines())


def report(results: list[BoxResult], total: int, wall: float) -> list[str]:
    lines = []
    for r in sorted(results, key=lambda r: r.index):
        f = box_figures(r.timeline)
        detail = (
            f"setup {f['setup_s']:.0f} s, tests {f['test_s']:.0f} s, cpu {f['cpu_test_s']:.0f} s in tests "
            f"({f['cpu_total_s']:.0f} s total), steal {f['steal_s']:.1f} s"
            if f
            else "no timings"
        )
        lines.append(f"box {r.index}/{total}: wall {r.wall:.0f} s, {r.tests} tests, rc {r.rc}, {detail}")
    figures = [f for f in (box_figures(r.timeline) for r in results) if f]
    lines.append(
        f"total: wall {wall:.0f} s, cpu {sum(f['cpu_total_s'] for f in figures):.0f} s over {len(figures)} boxes"
    )
    return lines


def _on_sigterm(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    cli = argparse.ArgumentParser(description="Run the full suite across up to 5 cloud sandboxes.")
    cli.add_argument("--boxes", type=int, default=MAX_BOXES)
    cli.add_argument("--workers", type=int, default=8, help="xdist workers per box (a box has 8 vCPUs)")
    cli.add_argument("--sha", default="HEAD")
    cli.add_argument("--minutes", type=int, default=15, help="wall-clock limit; a box past it is red")
    cli.add_argument("--out", type=Path, default=None)
    cli.add_argument(
        "--own-job",
        action="store_true",
        help="box 1 also runs the files CI's masking-gates job runs (tests/_shard.py OWN_JOB; no shard collects "
        "them, so the default run skips them); raise --minutes, they add about 8 minutes on that box",
    )
    return cli.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    started = time.monotonic()
    args = parse_args(argv)
    try:
        total = check_boxes(args.boxes)
    except ValueError as exc:
        print(exc)
        return 2
    sha = subprocess.check_output(["git", "rev-parse", args.sha], text=True).strip()
    if not pushed(sha):
        print(f"{sha} is not a ref tip on {REPO}: push it first; boxes clone it from GitHub.")
        return 2
    out_dir = args.out or Path(tempfile.mkdtemp(prefix=f"fleet-{sha[:9]}-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    global ledger
    ledger = load_ledger()
    if ledger is not None:
        try:
            ledger.preflight(total, TTL_S, ledger.RATE_LARGE)
        except (ledger.SpendCapError, ledger.LedgerError) as exc:
            print(f"fleet: the spend ledger refuses this run: {exc}")
            return 2
    sweep_stale()
    print(f"fleet: {total} boxes on {sha}, results in {out_dir}", flush=True)
    deadline = time.monotonic() + args.minutes * 60
    previous = signal.signal(signal.SIGTERM, _on_sigterm)
    stop.clear()
    try:
        with ThreadPoolExecutor(max_workers=total) as pool:
            try:
                results = list(
                    pool.map(
                        lambda k: run_box(k, total, sha, args.workers, out_dir, deadline, args.own_job),
                        range(1, total + 1),
                    )
                )
            except KeyboardInterrupt:
                stop.set()  # each box thread sees it within POLL_INTERVAL and removes its box
                raise
    finally:
        signal.signal(signal.SIGTERM, previous)
    code = exit_code(results, total)
    if code == 3:
        print(
            "fleet: NO VERDICT, no box ran its tests (credit, vCPU quota or an outage). Use CI; never retry in a loop."
        )
        return 3
    ok, lines = verdict(results, total)
    print("\n".join(lines + report(results, total, time.monotonic() - started)))
    print(f"fleet: {'GREEN' if ok else 'RED'} in {time.monotonic() - started:.0f} s")
    return code


if __name__ == "__main__":
    sys.exit(main())
