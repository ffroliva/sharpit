from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_the_heavy_masking_gates_have_one_job_and_no_shard_collects_them_passes_after_test_lane_gate(
    pytester: pytest.Pytester,
) -> None:
    result = pytester.runpytest(
        f"{ROOT}/tests/scripts/test_lane_gate.py::test_fixture_copy_never_writes_into_its_template",
        f"{ROOT}/tests/test_ci_layout.py::test_the_heavy_masking_gates_have_one_job_and_no_shard_collects_them",
    )
    result.assert_outcomes(passed=2)
