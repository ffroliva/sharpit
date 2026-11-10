"""Wall (a) last required check green and (b) last job done, attempt 1, per spec §7.1.

Metrics (from W0b-step0.md §2.1):
- Metric (a): Wall clock time in seconds from run created_at until the last required check
  turns green (or completes). The required checks enforced by GitHub branch protection are:
  test (ubuntu-latest, 3.12), test (ubuntu-latest, 3.13), test (ubuntu-latest, 3.14),
  test (windows-latest, 3.14), lowest, no-sqlalchemy, ui, vitest, wheel, coverage, sonar.
- Metric (b): Wall clock time in seconds from run created_at until the last job in the
  entire workflow completes (including masking-gates, masking-gates-check, and live database legs).
- Queue: started_at - created_at (run created_at for job start latency; job created_at for queue wait).
- In-job duration: completed_at - started_at.
- Step timings:
  - Setup: time from job started_at until the main test/work step begins.
  - Test: duration of the test/build/scan step.
  - Teardown: time from test completion until job completed_at.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_REQUIRED: frozenset[str] = frozenset(
    {
        "coverage",
        "lowest",
        "no-sqlalchemy",
        "sonar",
        "test (ubuntu-latest, 3.12)",
        "test (ubuntu-latest, 3.13)",
        "test (ubuntu-latest, 3.14)",
        "test (windows-latest, 3.14)",
        "ui",
        "vitest",
        "wheel",
    }
)


def parse_ts(s: str) -> datetime:
    """Parse an ISO-8601 timestamp string into a timezone-aware datetime."""
    return datetime.fromisoformat(s)


def runner_os(labels: Sequence[str]) -> str:
    """Infer runner OS identifier from job labels."""
    for lbl in labels:
        lower = lbl.lower()
        if "windows" in lower:
            return "windows"
        if "ubuntu" in lower or "linux" in lower:
            return "ubuntu"
        if "macos" in lower:
            return "macos"
    return "ubuntu"


@dataclass(frozen=True)
class JobTimings:
    name: str = ""
    os: str = ""
    queue: float = 0.0
    setup: float = 0.0
    test: float = 0.0
    teardown: float = 0.0
    duration: float = 0.0
    wall: float = 0.0
    conclusion: str = ""


@dataclass(frozen=True)
class Walls:
    a: float = 0.0
    b: float = 0.0
    max_queue: float = 0.0
    event: str = ""
    conclusion: str = ""
    run_id: int | str = ""
    per_job: dict[str, JobTimings] = field(default_factory=dict)
    per_os_critical: dict[str, str] = field(default_factory=dict)


def _step_timings(
    job_started_at: datetime,
    job_completed_at: datetime,
    steps: Sequence[dict[str, Any]],
) -> tuple[float, float, float]:
    """Calculate setup, test, and teardown durations in seconds."""
    total_dur = (job_completed_at - job_started_at).total_seconds()
    valid_steps = [s for s in steps if s.get("started_at") and s.get("completed_at")]
    if not valid_steps:
        return 0.0, total_dur, 0.0

    test_step: dict[str, Any] | None = None
    for s in valid_steps:
        sn = s.get("name", "").lower()
        if any(k in sn for k in ["pytest", "vitest", "sonarcloud scan", "npm run build"]):
            test_step = s
            break

    if test_step is not None:
        t_start = parse_ts(test_step["started_at"])
        t_end = parse_ts(test_step["completed_at"])
        setup = (t_start - job_started_at).total_seconds()
        test = (t_end - t_start).total_seconds()
        teardown = (job_completed_at - t_end).total_seconds()
        return setup, test, teardown

    return 0.0, total_dur, 0.0


def walls(
    run: dict[str, Any],
    jobs: list[dict[str, Any]] | None = None,
    required: Collection[str] | None = None,
) -> Walls:
    """Compute attempt-1 critical path walls (a) and (b), queue, and step timings."""
    run_dict: dict[str, Any] = run.get("run", run) if isinstance(run, dict) else run
    if jobs is None and "jobs" in run:
        jobs = run["jobs"]
    if jobs is None:
        jobs = []

    attempt = run_dict.get("run_attempt", 1)
    if attempt != 1:
        msg = f"walls only measures attempt 1, got attempt {attempt}"
        raise ValueError(msg)

    req_set = DEFAULT_REQUIRED if required is None else frozenset(required)
    run_created = parse_ts(run_dict["created_at"])
    run_event = run_dict.get("event", "")
    run_conclusion = run_dict.get("conclusion", "")
    run_id = run_dict.get("id", "")

    per_job: dict[str, JobTimings] = {}
    completed_jobs: list[tuple[dict[str, Any], datetime, datetime]] = []

    for j in jobs:
        j_attempt = j.get("run_attempt")
        if j_attempt not in (None, 1):
            msg = f"job {j.get('name')} is attempt {j_attempt}, expected attempt 1"
            raise ValueError(msg)
        if not j.get("completed_at") or not j.get("started_at"):
            continue
        j_start = parse_ts(j["started_at"])
        j_end = parse_ts(j["completed_at"])
        completed_jobs.append((j, j_start, j_end))

    if not completed_jobs:
        return Walls(event=run_event, conclusion=run_conclusion, run_id=run_id)

    b = (max(end for _, _, end in completed_jobs) - run_created).total_seconds()

    req_jobs = [(j, start, end) for j, start, end in completed_jobs if j["name"] in req_set]
    a = (max(end for _, _, end in req_jobs) - run_created).total_seconds() if req_jobs else 0.0

    max_queue = max((start - run_created).total_seconds() for _, start, _ in completed_jobs)

    latest_per_os: dict[str, tuple[str, datetime]] = {}

    for j, j_start, j_end in completed_jobs:
        name = j["name"]
        os_name = j.get("os") or runner_os(j.get("labels", []))
        queue = (j_start - run_created).total_seconds()
        dur = (j_end - j_start).total_seconds()
        wall = (j_end - run_created).total_seconds()
        setup, test, teardown = _step_timings(j_start, j_end, j.get("steps", []))

        per_job[name] = JobTimings(
            name=name,
            os=os_name,
            queue=queue,
            setup=setup,
            test=test,
            teardown=teardown,
            duration=dur,
            wall=wall,
            conclusion=j.get("conclusion", ""),
        )

        if os_name not in latest_per_os or j_end > latest_per_os[os_name][1]:
            latest_per_os[os_name] = (name, j_end)

    per_os_critical = {os_key: job_name for os_key, (job_name, _) in latest_per_os.items()}

    return Walls(
        a=a,
        b=b,
        max_queue=max_queue,
        event=run_event,
        conclusion=run_conclusion,
        run_id=run_id,
        per_job=per_job,
        per_os_critical=per_os_critical,
    )


def _extract_job_durations(r: Any) -> list[tuple[str, float]]:
    """Extract (job_name, duration) pairs from a run representation."""
    if isinstance(r, Walls):
        return [(name, jt.duration) for name, jt in r.per_job.items()]
    if not isinstance(r, dict):
        return []
    if "jobs" in r:
        pairs: list[tuple[str, float]] = []
        for j in r["jobs"]:
            if j.get("started_at") and j.get("completed_at"):
                dur = (parse_ts(j["completed_at"]) - parse_ts(j["started_at"])).total_seconds()
                pairs.append((j["name"], dur))
        return pairs
    if "per_job" in r:
        pairs = []
        for name, jt in r["per_job"].items():
            dur = jt.duration if isinstance(jt, JobTimings) else jt.get("duration", 0.0)
            pairs.append((name, dur))
        return pairs
    return []


def noise(runs: Sequence[Any]) -> dict[str, float]:
    """Return max - min duration per job across the runs."""
    durations_per_job: dict[str, list[float]] = {}
    for r in runs:
        for name, dur in _extract_job_durations(r):
            durations_per_job.setdefault(name, []).append(dur)

    result: dict[str, float] = {}
    for name, durs in durations_per_job.items():
        if durs:
            result[name] = round(max(durs) - min(durs), 3)
    return result


def _extract_values(items: Sequence[float | Any]) -> list[float]:
    values: list[float] = []
    for item in items:
        if isinstance(item, (int, float)):
            values.append(float(item))
        elif hasattr(item, "b"):
            values.append(float(item.b))
        elif isinstance(item, dict) and "b" in item:
            values.append(float(item["b"]))
        else:
            values.append(float(item))
    return values


def gain(before: Sequence[float | Any], after: Sequence[float | Any]) -> bool:
    """Return True if and only if after-max < before-min."""
    b_vals = _extract_values(before)
    a_vals = _extract_values(after)
    if not b_vals or not a_vals:
        return False
    return max(a_vals) < min(b_vals)


def _fetch_gh_json(*args: str) -> Any:
    out = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Attempt-1 CI critical-path table from run ids per spec §7.1")
    parser.add_argument("run_ids", nargs="+", help="Run ids or paths to JSON files")
    parser.add_argument(
        "--required-from-protection",
        action="store_true",
        help="Query GitHub API for required status checks from main branch protection",
    )
    args = parser.parse_args()

    required = DEFAULT_REQUIRED
    if args.required_from_protection:
        try:
            prot = _fetch_gh_json("api", "repos/ffroliva/sharpit/branches/main/protection/required_status_checks")
            required = frozenset(prot.get("contexts", []))
        except subprocess.CalledProcessError:
            pass

    wall_runs: list[Walls] = []
    for run_arg in args.run_ids:
        path = Path(run_arg)
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            w = walls(data["run"], data["jobs"], required)
        else:
            run_obj = _fetch_gh_json("api", f"repos/ffroliva/sharpit/actions/runs/{run_arg}/attempts/1")
            jobs_obj = _fetch_gh_json(
                "api", f"repos/ffroliva/sharpit/actions/runs/{run_arg}/attempts/1/jobs", "--paginate"
            )
            w = walls(run_obj, jobs_obj.get("jobs", []), required)
        wall_runs.append(w)

        slowest = sorted(w.per_job.values(), key=lambda j: j.duration, reverse=True)[:4]
        slow_str = ", ".join(f"{j.name} {int(j.duration)}s" for j in slowest)
        print(
            f"{w.run_id} {w.conclusion}: (a) {int(w.a)}s ({w.a / 60:.2f} min) "
            f"(b) {int(w.b)}s ({w.b / 60:.2f} min) max-queue {int(w.max_queue)}s | slowest: {slow_str}"
        )

    if len(wall_runs) > 1:
        n = noise(wall_runs)
        print("\nTop 5 noise (max - min in-job duration across runs):")
        for jname, diff in sorted(n.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  {jname}: {diff:.1f}s")


if __name__ == "__main__":
    main()
