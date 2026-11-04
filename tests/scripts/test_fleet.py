"""scripts/ci/fleet.py: the pure parts (verdict, exit codes, box count, timings). No network, no `sbx`."""

import pytest
from _load import load_script

fleet = load_script("scripts/ci/fleet.py")
SHA = "a" * 40


def ok(index: int) -> object:
    return fleet.BoxResult(index, rc=0, tests=10)


def stat(user: int, system: int = 0, idle: int = 0, steal: int = 0) -> str:
    return f"cpu {user} 0 {system} {idle} 0 0 0 {steal} 0 0"


def line(label: str, epoch_ms: int, cpu: str) -> str:
    return f"{label} {epoch_ms} {cpu}\n"


def test_all_boxes_green_is_exit_0():
    assert fleet.exit_code([ok(1), ok(2)], 2) == 0


def test_no_stage_is_exit_3():
    assert fleet.exit_code([fleet.BoxResult(1), fleet.BoxResult(2)], 2) == 3


def test_no_boxes_at_all_is_exit_3():
    assert fleet.exit_code([], 5) == 3


def test_failed_pytest_is_exit_1():
    assert fleet.exit_code([ok(1), fleet.BoxResult(2, rc=1, tests=10)], 2) == 1


def test_a_box_failure_is_never_exit_3():
    assert fleet.exit_code([fleet.BoxResult(1, fatal="clone-failed")], 1) == 1


def test_a_missing_box_is_red_when_another_ran():
    assert fleet.exit_code([ok(1)], 2) == 1


def test_missing_box_is_named():
    _, lines = fleet.verdict([ok(1)], 2)
    assert lines == ["box 2/2 returned no result"]


def test_box_that_ran_no_tests_is_red():
    assert fleet.exit_code([fleet.BoxResult(1, rc=0, tests=0)], 1) == 1


def test_pytest_no_tests_collected_is_red():
    assert fleet.exit_code([fleet.BoxResult(1, rc=5, tests=0)], 1) == 1


@pytest.mark.parametrize("count", [1, 5])
def test_box_count_in_range_is_accepted(count: int):
    assert fleet.check_boxes(count) == count


@pytest.mark.parametrize("count", [0, 6, -1])
def test_box_count_out_of_range_is_refused(count: int):
    with pytest.raises(ValueError, match="1 to 5"):
        fleet.check_boxes(count)


def test_six_boxes_exits_2_before_touching_anything():
    assert fleet.main(["--boxes", "6"]) == 2


def test_box_script_carries_its_shard():
    assert "SHARPIT_SHARD=3/5 " in fleet.box_script(3, 5, 8, SHA)


def test_box_script_checks_out_the_sha_with_a_full_clone():
    script = fleet.box_script(1, 5, 8, SHA)
    assert f"git checkout -q {SHA}" in script
    assert "--filter" not in script


def test_box_script_has_no_unfilled_placeholder():
    assert "@" not in fleet.box_script(1, 5, 8, SHA).replace("@REPO@", "")


def test_box_script_refuses_a_ref_name():
    with pytest.raises(ValueError, match="full sha"):
        fleet.box_script(1, 5, 8, "main; rm -rf ~")


def test_box_script_reads_no_local_secret():
    script = fleet.box_script(1, 5, 8, SHA)
    assert ".env" not in script
    assert "token" not in script.lower()


def test_stale_boxes_keeps_only_fleet_names():
    text = (
        "SANDBOX                AGENT  ID   STATUS\n"
        "shell/fleet-abc123456-9-1of5  shell  sbx_1  running\n"
        "shell/other  shell  sbx_2  running\n"
    )
    assert fleet.stale_boxes(text) == ["fleet-abc123456-9-1of5"]


def test_stale_boxes_empty_listing():
    assert fleet.stale_boxes("No sandboxes found\n") == []


def test_busy_seconds_ignores_idle_and_steal():
    a = [100, 0, 50, 900, 0, 0, 0, 5, 0, 0]
    b = [300, 0, 150, 1500, 0, 0, 0, 25, 0, 0]
    assert fleet.busy_seconds(a, b) == 3.0


def test_steal_seconds():
    assert fleet.steal_seconds([0] * 10, [0, 0, 0, 0, 0, 0, 0, 50, 0, 0]) == 0.5


def test_box_figures_split_setup_and_tests():
    timeline = (
        line("start", 1_000_000, stat(0))
        + line("tests_begin", 1_005_000, stat(100))
        + line("tests_end", 1_025_000, stat(1100, 100))
    )
    figures = fleet.box_figures(timeline)
    assert figures["setup_s"] == 5.0
    assert figures["test_s"] == 20.0
    assert figures["cpu_test_s"] == 11.0
    assert figures["cpu_total_s"] == 12.0


def test_box_figures_without_tests_is_none():
    assert fleet.box_figures(line("start", 1, stat(0))) is None


def test_timeline_marks_skips_a_cut_line():
    assert fleet.timeline_marks("start 12 cpu 1 2") == {}
