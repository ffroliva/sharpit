"""scripts/ci/shard_weights.py: JUnit artifacts to per-file weights; the folder also holds the gates reports."""

from pathlib import Path

from _load import load_script

shard_weights = load_script("scripts/ci/shard_weights.py")

CASE = '<testsuite><testcase classname="tests.engine.test_guard.TestX" name="t" time="{seconds}"/></testsuite>'


def _report(root: Path, artifact: str, seconds: float) -> None:
    folder = root / artifact
    folder.mkdir(parents=True)
    (folder / "junit.xml").write_text(CASE.format(seconds=seconds), encoding="utf-8")


def test_a_gates_artifact_beside_the_shard_artifacts_is_not_a_shard_leg(tmp_path: Path) -> None:
    _report(tmp_path, "junit-ubuntu-latest-3.12-1", 4.0)
    _report(tmp_path, "junit-gates-ubuntu-latest", 900.0)
    _report(tmp_path, "junit-gates-windows-latest", 900.0)
    try:
        table = shard_weights.weights(tmp_path)
    except Exception as exc:  # noqa: BLE001 - the crash is the defect; the assertion below must name it
        table = {"crashed": {type(exc).__name__: 0.0}}
    assert table == {"linux": {"tests/engine/test_guard.py": 4.0}}
