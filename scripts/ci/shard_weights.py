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


def test_file(classname: str) -> str:
    """``tests.engine.test_guard.TestX`` -> ``tests/engine/test_guard.py``."""
    parts = classname.split(".")
    while parts and not parts[-1].startswith("test_"):
        parts.pop()
    return "/".join(parts) + ".py"


def weights(root: Path) -> dict[str, dict[str, float]]:
    # artifact dirs are junit-<os>-<python>-<job index>: one leg is <os>-<python>
    per_leg: dict[str, dict[str, defaultdict[str, float]]] = defaultdict(dict)
    for report in sorted(root.glob("junit-*/junit.xml")):
        os_name, python = report.parent.name.split("-")[1], report.parent.name.split("-")[3]
        platform = next(p for key, p in PLATFORMS.items() if os_name.startswith(key))
        leg = per_leg[platform].setdefault(python, defaultdict(float))
        for case in ET.parse(report).iter("testcase"):
            leg[test_file(case.get("classname", ""))] += float(case.get("time", 0))
    table: dict[str, dict[str, float]] = {}
    for platform, legs in sorted(per_leg.items()):
        files = sorted({f for leg in legs.values() for f in leg})
        table[platform] = {f: round(sum(leg.get(f, 0.0) for leg in legs.values()) / len(legs), 1) for f in files}
    return table


if __name__ == "__main__":
    OUT.write_text(json.dumps(weights(Path(sys.argv[1])), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
