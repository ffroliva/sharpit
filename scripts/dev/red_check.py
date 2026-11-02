"""Check that each red test fails for the right reason before a ``test:`` commit.

    uv run python scripts/dev/red_check.py <node id> [<node id> ...]

Runs the given tests in the current tree and environment and prints one verdict per test:

- ``RED (assertion in test file)``: a valid red;
- ``CRASH (<ExceptionType> ...)``: a TypeError/AttributeError/ImportError stub, or an ``assert`` inside ``src``: not
  a red, use a wrong-value stub (return the wrong state) so the test's own assertion fails;
- ``PASS (not a red)``: the test does not fail (or was skipped);
- ``ERROR (collection)``: the test errored or was not collected.

Exit 0 only when every test is a valid red. The classification is lane_gate.py's own, imported, so this check and the
merge gate cannot disagree.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# private on purpose: the merge gate's own classification, imported so the two can never drift apart
from lane_gate import _outcomes  # noqa: E402

RED = "RED (assertion in test file)"


def _verdict(outcome: str, detail: str) -> str:
    if outcome == "failure":
        return (
            RED
            if detail == "AssertionError"
            else f"CRASH ({detail or 'unnamed exception'} — not a red: use a wrong-value stub)"
        )
    if outcome in ("passed", "skipped"):
        return "PASS (not a red)"
    return "ERROR (collection)"


def check(nodeids: Sequence[str], cwd: Path | None = None) -> dict[str, str]:
    """nodeid -> verdict; a parametrised id is red only when every case is."""
    with tempfile.TemporaryDirectory(prefix="red-check-") as scratch:
        junit = Path(scratch) / "junit.xml"
        command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:randomly", "--tb=long"]
        subprocess.run([*command, f"--junitxml={junit}", *nodeids], cwd=cwd, capture_output=True, check=False)
        outcomes = _outcomes(junit, nodeids)
    verdicts: dict[str, str] = {}
    for nodeid, cases in outcomes.items():
        found = [_verdict(o, m) for o, m in cases]
        verdicts[nodeid] = next((v for v in found if v != RED), RED)
    return verdicts


def main(argv: Sequence[str] | None = None) -> int:
    nodeids = list(sys.argv[1:] if argv is None else argv)
    if not nodeids:
        print(__doc__)
        return 2
    verdicts = check(nodeids)
    for nodeid, verdict in verdicts.items():
        print(f"{verdict}  {nodeid}")
    return 0 if all(v == RED for v in verdicts.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
