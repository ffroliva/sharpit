#!/usr/bin/env python3
"""Require genuine, successful live-database test execution, not a no-server skip.

    check_live_tests.py <junit.xml> --require <test function>[=<case count>] [...]

Ported from BootUI's ``.github/scripts/check-mysql-live-tests.py``. BootUI names JUnit classes in Surefire reports;
pytest names functions, so a required "suite" is a test function name, and every case of it (``name[param]``) counts.
Exit 0 only when each required function has cases (exactly ``=N`` of them when given), the suite counters agree with
its cases and report no failure, error or skip, and no case failed, errored or was skipped.
"""

import argparse
import re
import sys
import xml.etree.ElementTree as ET  # noqa: S405 - the report is pytest's own output, written in this job
from collections.abc import Sequence
from pathlib import Path

STATES = ("failure", "error", "skipped")
ORACLE_LEG = re.compile(r"test_oracle_row\[(\w+)-(\w+)-\d+\]$")


def check(report: Path, required: Sequence[str], legs: Sequence[str] = ()) -> list[str]:  # noqa: C901 - one linear sequence of report checks
    try:
        root = ET.parse(report).getroot()  # noqa: S314 - as above
    except (ET.ParseError, OSError) as error:
        return [f"Cannot read test report {report.name}: {type(error).__name__}"]
    failures: list[str] = []
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    for suite in suites:
        try:
            counts = {key: int(suite.get(key, "0")) for key in ("tests", "failures", "errors", "skipped")}
        except ValueError:
            failures.append("invalid test counters")
            continue
        if counts["tests"] != len(list(suite.iter("testcase"))):
            failures.append("inconsistent test counters")
        elif any(counts[key] for key in ("failures", "errors", "skipped")):
            failures.append("the suite counters report a failure, error or skip")
    cases = [case for suite in suites for case in suite.iter("testcase")]
    for spec in required:
        name, _, wanted = spec.partition("=")
        mine = [case for case in cases if case.get("name", "").split("[", 1)[0] == name]
        if not mine:
            failures.append(f"{name}: no executed test cases")
        elif wanted and len(mine) != int(wanted):
            failures.append(f"{name}: expected {wanted} cases, found {len(mine)}")
        elif any(case.find(state) is not None for case in mine for state in STATES):
            failures.append(f"{name}: every required live test must pass without skips")
    rows = [case for case in cases if ORACLE_LEG.fullmatch(case.get("name", ""))]
    for spec in legs:
        name, _, wanted = spec.partition("=")
        mine = [
            case
            for case in rows
            if (match := ORACLE_LEG.fullmatch(case.get("name", ""))) and f"{match[1]}-{match[2]}" == name
        ]
        if len(mine) != int(wanted):
            failures.append(f"{name}: expected {wanted} cases, found {len(mine)}")
        elif not any(
            prop.get("name") == "returned" and prop.get("value", "").lower() == "true"
            for case in mine
            for prop in case.iter("property")
        ):
            failures.append(f"{name}: no row returned its marker")
    return failures


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--require", nargs="+", required=True, help="Required test function names")
    parser.add_argument("--legs", nargs="*", default=(), help="Pinned oracle leg counts as key-session=count")
    arguments = parser.parse_args(argv)
    failures = check(arguments.report, arguments.require, arguments.legs)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"Live evidence: {len(arguments.require)} required tests passed without skips.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
