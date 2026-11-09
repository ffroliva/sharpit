"""Write tests/shard_weights.json from CI test-shard JUnit artifacts (``gh run download <id> -p 'junit-*' -D <dir>``).

Weights are seconds of test time per test file and platform, averaged over the legs of that platform. They only
balance the CI shards (tests/_shard.py); the pytest-speed baseline stays tests/test_durations.json.

    python scripts/ci/shard_weights.py <dir>
"""

import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "tests" / "shard_weights.json"
PLATFORMS = {"windows": "win32", "ubuntu": "linux"}
JOBS = ("test-shard", "coverage-shard", "lowest-shard", "no-sqlalchemy-shard", "masking-gates", "live", "sharpit-gate")


def parse_artifact(name: str) -> tuple[str, str] | None:
    """Return the pytest job and leg from ``junit-`` or ``overhead-`` artifact names."""
    prefix = next((prefix for prefix in ("junit-", "overhead-") if name.startswith(prefix)), None)
    if prefix is None:
        return None
    artifact = name.removeprefix(prefix)
    for job in JOBS:
        if artifact.startswith(f"{job}-"):
            return job, artifact.removeprefix(f"{job}-")
    return None


def test_file(classname: str) -> str:
    """``tests.engine.test_guard.TestX`` -> ``tests/engine/test_guard.py``."""
    parts = classname.split(".")
    while parts and not parts[-1].startswith("test_"):
        parts.pop()
    return "/".join(parts) + ".py"


def weights(root: Path) -> dict[str, dict[str, float]]:
    # Test-shard JUnit artifacts end in <os>-<python>-<job index>; the middle is the averaging leg.
    per_leg: dict[str, dict[str, defaultdict[str, float]]] = defaultdict(dict)
    for report in sorted(root.glob("junit-*/junit.xml")):
        parsed = parse_artifact(report.parent.name)
        if parsed is None or parsed[0] != "test-shard":
            continue  # junit-gates-<os> (masking-gates job) is no shard leg
        leg = parsed[1].split("-")
        if len(leg) < 3 or leg[0] not in PLATFORMS:
            continue
        os_name, python = leg[0], leg[2]
        platform = PLATFORMS[os_name]
        leg = per_leg[platform].setdefault(python, defaultdict(float))
        for case in ET.parse(report).iter("testcase"):
            leg[test_file(case.get("classname", ""))] += float(case.get("time", 0))
    table: dict[str, dict[str, float]] = {}
    for platform, legs in sorted(per_leg.items()):
        files = sorted({f for leg in legs.values() for f in leg})
        table[platform] = {f: round(sum(leg.get(f, 0.0) for leg in legs.values()) / len(legs), 1) for f in files}
    return table


if __name__ == "__main__":
    text = json.dumps(weights(Path(sys.argv[1])), indent=1, sort_keys=True) + "\n"
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT}")
