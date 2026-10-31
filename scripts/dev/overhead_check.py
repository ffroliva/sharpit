"""Diagnose whether overhead budget failures are larger than the measured machine noise.

Usage: ``uv run python -m scripts.dev.overhead_check <pytest node id or file> [--runs N] [--load]``
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import statistics
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

WITHIN_BUDGET = "within budget"
FLAKY = "flaky: failures are within the noise, suspect the machine, not the code"
OVER_BUDGET = "over budget: a failure is larger than its noise, treat as a real regression"


def classify(records: Sequence[dict[str, Any]]) -> str:
    """Classify a set of check_budget JSON records using each failed run's noise estimate."""
    failures = [record for record in records if record["verdict"] == "OVER"]
    if not failures:
        return WITHIN_BUDGET
    if all(record["overhead"] - record["budget"] <= record["noise"] for record in failures):
        return FLAKY
    return OVER_BUDGET


def read_records(path: str | Path) -> list[dict[str, Any]]:
    """Read all non-empty JSON lines written by ``tests.overhead.check_budget``."""
    with Path(path).open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _bursty_load(stop: multiprocessing.synchronize.Event) -> None:
    """Keep one core busy for 0.7 seconds, then idle for 0.7 seconds until stopped."""
    while not stop.is_set():
        busy_until = time.perf_counter() + 0.7
        while time.perf_counter() < busy_until and not stop.is_set():
            pass
        stop.wait(0.7)


def _start_load() -> tuple[multiprocessing.synchronize.Event, list[multiprocessing.Process]]:
    stop = multiprocessing.Event()
    processes: list[multiprocessing.Process] = []
    try:
        for _ in range(os.cpu_count() or 1):
            process = multiprocessing.Process(target=_bursty_load, args=(stop,), daemon=True)
            process.start()
            processes.append(process)
    except BaseException:
        _stop_load(stop, processes)
        raise
    return stop, processes


def _stop_load(stop: multiprocessing.synchronize.Event, processes: list[multiprocessing.Process]) -> None:
    stop.set()
    for process in processes:
        process.join(timeout=1)
        if process.is_alive():
            process.terminate()
            process.join()


def _positive_int(value: str) -> int:
    runs = int(value)
    if runs < 1:
        raise argparse.ArgumentTypeError("runs must be at least 1")
    return runs


def _print_summary(records: list[dict[str, Any]]) -> bool:
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_name[record["name"]].append(record)

    regression = False
    for name, named_records in by_name.items():
        overheads = [record["overhead"] for record in named_records]
        noises = [record["noise"] for record in named_records]
        failures = sum(record["verdict"] == "OVER" for record in named_records)
        verdict = classify(named_records)
        regression |= verdict == OVER_BUDGET
        print(
            f"{name}: runs={len(named_records)} failures={failures} "
            f"overhead min/median/max={min(overheads):.3f}/{statistics.median(overheads):.3f}/"
            f"{max(overheads):.3f} noise median={statistics.median(noises):.3f} "
            f"budget={named_records[0]['budget']:.3f}; {verdict}"
        )
    return regression


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="pytest node id or file to run")
    parser.add_argument("--runs", type=_positive_int, default=10, help="number of pytest runs (default: 10)")
    parser.add_argument("--load", action="store_true", help="run bursty CPU load during the measurements")
    args = parser.parse_args(argv)

    load_stop: multiprocessing.synchronize.Event | None = None
    load_processes: list[multiprocessing.Process] = []
    records: list[dict[str, Any]] = []
    failed_without_budget_record = False
    try:
        if args.load:
            load_stop, load_processes = _start_load()
        with tempfile.TemporaryDirectory(prefix="sharpit-overhead-") as temp_dir:
            for run in range(args.runs):
                log_path = Path(temp_dir) / f"run-{run + 1}.jsonl"
                env = os.environ.copy()
                env["SHARPIT_OVERHEAD_LOG"] = str(log_path)
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", args.target],
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                run_records = read_records(log_path) if log_path.exists() else []
                records.extend(run_records)
                if result.returncode and not any(record["verdict"] == "OVER" for record in run_records):
                    failed_without_budget_record = True
                    if result.stdout:
                        print(result.stdout, file=sys.stderr, end="")
                    if result.stderr:
                        print(result.stderr, file=sys.stderr, end="")
    finally:
        if load_stop is not None:
            _stop_load(load_stop, load_processes)

    regression = _print_summary(records)
    if not records and failed_without_budget_record:
        print("No overhead records were produced; pytest failed.", file=sys.stderr)
    return 1 if regression or failed_without_budget_record else 0


if __name__ == "__main__":
    sys.exit(main())
