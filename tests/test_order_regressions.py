from pathlib import Path

import pytest

from test_ci_layout import OWN_JOB_FILES

ROOT = Path(__file__).resolve().parents[1]
VICTIM = f"{ROOT}/tests/test_ci_layout.py::test_the_heavy_masking_gates_have_one_job_and_no_shard_collects_them"


@pytest.mark.parametrize("gate", OWN_JOB_FILES)
def test_heavy_masking_layout_test_passes_after_each_gate(gate: str, pytester: pytest.Pytester) -> None:
    result = pytester.runpytest_subprocess(
        str(ROOT / gate),
        VICTIM,
        "-k",
        "test_the_heavy_masking_gates_have_one_job_and_no_shard_collects_them",
        "-n",
        "0",
        "-p",
        "no:cacheprovider",
    )
    result.assert_outcomes(passed=2)
