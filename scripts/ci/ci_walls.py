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
import sys
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
    a: float | None = 0.0
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
        if any(k in sn for k in ["pytest", "vitest", "sonarcloud scan", "npm run build", "test", "build"]):
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


def _parse_run(run: dict[str, Any]) -> datetime:
    attempt = run.get("run_attempt", 1)
    if attempt != 1:
        msg = f"walls only measures attempt 1, got attempt {attempt}"
        raise ValueError(msg)
    return parse_ts(run["created_at"])


def _parse_jobs(jobs: Sequence[dict[str, Any]]) -> list[tuple[dict[str, Any], datetime, datetime]]:
    completed: list[tuple[dict[str, Any], datetime, datetime]] = []
    for j in jobs:
        j_attempt = j.get("run_attempt")
        if j_attempt not in (None, 1):
            msg = f"job {j.get('name')} is attempt {j_attempt}, expected attempt 1"
            raise ValueError(msg)
        if not j.get("completed_at") or not j.get("started_at"):
            continue
        completed.append((j, parse_ts(j["started_at"]), parse_ts(j["completed_at"])))
    return completed


def _per_job_timings(
    run_created: datetime,
    completed_jobs: Sequence[tuple[dict[str, Any], datetime, datetime]],
) -> tuple[dict[str, JobTimings], dict[str, str]]:
    per_job: dict[str, JobTimings] = {}
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
    return per_job, {os_name: name for os_name, (name, _) in latest_per_os.items()}


def _aggregate_walls(
    run: dict[str, Any],
    run_created: datetime,
    jobs: Sequence[dict[str, Any]],
    completed_jobs: Sequence[tuple[dict[str, Any], datetime, datetime]],
    required: Collection[str],
    per_job: dict[str, JobTimings],
    per_os_critical: dict[str, str],
) -> Walls:
    if not completed_jobs:
        return Walls(event=run.get("event", ""), conclusion=run.get("conclusion", ""), run_id=run.get("id", ""))
    required_jobs = [job for job in jobs if job["name"] in required]
    if any(job.get("conclusion") != "success" for job in required_jobs):
        a = None
    else:
        required_ends = [end for job, _, end in completed_jobs if job["name"] in required]
        a = (max(required_ends) - run_created).total_seconds() if required_ends else 0.0
    b = (max(end for _, _, end in completed_jobs) - run_created).total_seconds()
    max_queue = max((start - run_created).total_seconds() for _, start, _ in completed_jobs)
    return Walls(
        a=a,
        b=b,
        max_queue=max_queue,
        event=run.get("event", ""),
        conclusion=run.get("conclusion", ""),
        run_id=run.get("id", ""),
        per_job=per_job,
        per_os_critical=per_os_critical,
    )


def walls(run: dict[str, Any], jobs: Sequence[dict[str, Any]], required: Collection[str] | None = None) -> Walls:
    """Compute attempt-1 critical path walls (a) and (b), queue, and step timings."""
    run_created = _parse_run(run)
    completed_jobs = _parse_jobs(jobs)
    per_job, per_os_critical = _per_job_timings(run_created, completed_jobs)
    req_set = DEFAULT_REQUIRED if required is None else frozenset(required)
    return _aggregate_walls(run, run_created, jobs, completed_jobs, req_set, per_job, per_os_critical)


def noise(runs: Sequence[Walls]) -> dict[str, float]:
    """Return max - min duration per job across the runs."""
    durations_per_job: dict[str, list[float]] = {}
    for run in runs:
        for name, timings in run.per_job.items():
            durations_per_job.setdefault(name, []).append(timings.duration)

    result: dict[str, float] = {}
    for name, durs in durations_per_job.items():
        if durs:
            result[name] = round(max(durs) - min(durs), 3)
    return result


def gain(before: Sequence[float], after: Sequence[float]) -> bool:
    """Return True if and only if after-max < before-min."""
    if not before or not after:
        return False
    return max(after) < min(before)


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
        except subprocess.CalledProcessError as exc:
            print(f"warning: failed to read required checks from branch protection: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

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
        a_str = "undefined" if w.a is None else f"{int(w.a)}s ({w.a / 60:.2f} min)"
        print(
            f"{w.run_id} {w.conclusion}: (a) {a_str} (b) {int(w.b)}s ({w.b / 60:.2f} min) max-queue "
            f"{int(w.max_queue)}s | slowest: {slow_str}"
        )

    if len(wall_runs) > 1:
        n = noise(wall_runs)
        print("\nTop 5 noise (max - min in-job duration across runs):")
        for jname, diff in sorted(n.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  {jname}: {diff:.1f}s")


if __name__ == "__main__":
    main()
