"""scripts/ci/fleet.py: the pure parts (verdict, exit codes, box count, timings). No network, no `sbx`."""

import os
import subprocess

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


def test_sbx_disables_interactive_prompts(monkeypatch: pytest.MonkeyPatch):
    calls = []

    def run(command: list[str], **kwargs: object) -> object:
        calls.append((command, kwargs))
        return object()

    monkeypatch.setattr(fleet.subprocess, "run", run)
    fleet._sbx("create", "shell", stdin="answer", timeout=123)

    assert calls[0][0] == ["sbx", "--no-input", "--cloud", "create", "shell"]
    kwargs = calls[0][1]
    assert kwargs["input"] == "answer"
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["timeout"] == 123
    assert kwargs["env"] == {**os.environ, "GODEBUG": "tlsmlkem=0", "MSYS_NO_PATHCONV": "1"}


def test_create_passes_network_allowlist_on_single_create_call(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(fleet, "ttl_s", 30 * 60)  # the run's TTL, set by main from the history
    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "sbx_1\n", "")

    monkeypatch.setattr(fleet.subprocess, "run", run)
    result = fleet._create("fleet-abc123456-9-1of5")

    assert result.returncode == 0
    assert result.stdout == "sbx_1\n"
    assert calls == [
        [
            "sbx",
            "--no-input",
            "--cloud",
            "create",
            "shell",
            "--name",
            "fleet-abc123456-9-1of5",
            "--cpus",
            "8",
            "--memory",
            "16g",
            "--ttl",
            "30m",
            "--on-timeout",
            "delete",
            "--no-progress",
            "--allow-network",
            "github.com",
            "--allow-network",
            "**.githubusercontent.com",
            "--allow-network",
            "pypi.org",
            "--allow-network",
            "files.pythonhosted.org",
            "--allow-network",
            "astral.sh",
            "--allow-network",
            "**.astral.sh",
        ],
    ]
    assert [c for c in calls if "policy" in c] == []
    assert calls[0][-12:] == [a for host in fleet.NETWORK for a in ("--allow-network", host)]


def test_create_returns_direct_failure_result(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(fleet, "ttl_s", 30 * 60)  # the run's TTL, set by main from the history
    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, "", "quota exceeded\n")

    monkeypatch.setattr(fleet.subprocess, "run", run)
    result = fleet._create("fleet-abc123456-9-2of5")

    assert result.returncode == 1
    assert result.stderr == "quota exceeded\n"
    assert calls == [
        [
            "sbx",
            "--no-input",
            "--cloud",
            "create",
            "shell",
            "--name",
            "fleet-abc123456-9-2of5",
            "--cpus",
            "8",
            "--memory",
            "16g",
            "--ttl",
            "30m",
            "--on-timeout",
            "delete",
            "--no-progress",
            *[a for host in fleet.NETWORK for a in ("--allow-network", host)],
        ],
    ]


@pytest.mark.parametrize(
    ("stderr", "cause"),
    [
        (
            "failed: dial tcp: lookup production.cloudfront.docker.com: no such host "
            "https://production.cloudfront.docker.com/file?X-Amz-Signature=secret",
            "dns",
        ),
        ("dial tcp 10.0.0.1:443: connection refused", "network"),
        ("failed to connect: sandboxd socket not found", "daemon"),
        ("Error: unauthorized (401); please login", "auth"),
        ("quota exceeded: vCPU limit exceeded", "quota"),
        ("insufficient credit: billing required", "credit"),
        ("create failed for an unclassified reason", "unknown"),
    ],
)
def test_create_failure_cause(stderr: str, cause: str):
    assert fleet.create_failure_cause(stderr) == cause


def test_create_failure_excerpt_keeps_reason_and_drops_signed_query():
    stderr = (
        "dial tcp: lookup production.cloudfront.docker.com: no such host https://host/file?X-Amz-Signature=" + "x" * 400
    )
    excerpt = fleet.create_failure_excerpt(stderr)
    assert "no such host" in excerpt
    assert "X-Amz-Signature" not in excerpt


def test_no_box_message_names_create_failure_cause():
    message = fleet.no_box_message([fleet.BoxResult(1, create_cause="dns")])
    assert "1 create failure (dns)" in message


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


class FakeSbx:
    """`sbx` with a scripted inventory: `listed` holds the `sbx ls` answers in order, the last one repeats."""

    def __init__(self, listed: list[list[str]], rm_rc: int = 0, create: object = None):
        self.listed, self.rm_rc, self.create, self.calls = listed, rm_rc, create, []

    def __call__(self, *args: str, timeout: int = 300, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        if args[0] == "ls":
            names = self.listed.pop(0) if len(self.listed) > 1 else self.listed[0]
            rows = "".join(f"shell/{n}  shell  sbx_1  running\n" for n in names)
            return subprocess.CompletedProcess(args, 0, "SANDBOX  AGENT  ID  STATUS\n" + rows, "")
        if args[0] == "rm":
            return subprocess.CompletedProcess(args, self.rm_rc, "", "")
        if args[0] == "create" and isinstance(self.create, BaseException):
            raise self.create
        return subprocess.CompletedProcess(args, 1, "", "create refused")


class FakeLedger:
    RATE_LARGE = 0.00016

    def __init__(self):
        self.rows: list[tuple[str, float, str]] = []

    def record(self, name: str, seconds: float, rate: float, basis: str = "measured") -> None:
        self.rows.append((name, seconds, basis))


@pytest.fixture
def no_wait(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(fleet.time, "sleep", lambda _s: None)


def test_a_box_absent_from_the_inventory_is_released_even_when_rm_fails(monkeypatch: pytest.MonkeyPatch, no_wait):
    sbx = FakeSbx(listed=[[]], rm_rc=1)  # create timed out: the box never existed, so `rm -f` has nothing to remove
    monkeypatch.setattr(fleet, "_sbx", sbx)
    assert fleet._release("fleet-abc-1-1of5") is True


def test_release_removes_and_rechecks_until_the_inventory_is_clean(monkeypatch: pytest.MonkeyPatch, no_wait):
    name = "fleet-abc-1-1of5"
    sbx = FakeSbx(listed=[[name], [name], []])
    monkeypatch.setattr(fleet, "_sbx", sbx)
    fleet._release(name)
    assert [c[0] for c in sbx.calls].count("rm") == 3


def test_a_box_still_listed_after_every_try_is_not_released(monkeypatch: pytest.MonkeyPatch, no_wait, capsys):
    name = "fleet-abc-1-1of5"
    monkeypatch.setattr(fleet, "_sbx", FakeSbx(listed=[[name]]))
    assert fleet._release(name) is False
    assert f"BOX LEFT RUNNING: {name}" in capsys.readouterr().out


def test_a_create_timeout_with_no_box_is_charged_measured_not_ttl(monkeypatch: pytest.MonkeyPatch, no_wait, tmp_path):
    monkeypatch.setattr(fleet, "_sbx", FakeSbx(listed=[[]], rm_rc=1, create=subprocess.TimeoutExpired("sbx", 300)))
    book = FakeLedger()
    monkeypatch.setattr(fleet, "ledger", book)
    fleet.run_box(1, 5, SHA, 8, tmp_path, deadline=0.0)
    assert [basis for _n, _s, basis in book.rows] == ["measured"]


def test_the_run_ends_with_no_box_of_its_own_left(monkeypatch: pytest.MonkeyPatch, no_wait):
    mine, other = f"{fleet.NAME_PREFIX}{SHA[:9]}-{os.getpid()}-2of5", "fleet-bbbbbbbbb-1-1of5"
    sbx = FakeSbx(listed=[[mine, other], [other]])
    monkeypatch.setattr(fleet, "_sbx", sbx)
    assert fleet.release_own(SHA) == []
    assert ("rm", "-f", mine) in sbx.calls


# The box TTL follows the measured runs (owner 2026-11-07): the slowest box of recent runs, with room, never an hour
def test_the_ttl_follows_the_slowest_box_of_recent_runs():
    assert fleet.ttl_for([82.0, 79.0, 73.0, 77.0, 86.0]) == 5 * 60  # median 79 s x 1.5 + 120 s, up to a 5 min floor


def test_a_slower_history_gets_a_longer_ttl():
    assert fleet.ttl_for([200.0]) == 7 * 60  # 200 x 1.5 + 120 = 420 s


def test_the_ttl_never_passes_its_cap():
    assert fleet.ttl_for([1500.0]) == 30 * 60


def test_no_history_gives_the_default_ttl_not_the_cap():
    assert fleet.ttl_for([]) == 10 * 60


def test_the_deadline_leaves_the_slack_to_collect_before_the_ttl():
    assert fleet.deadline_for(5 * 60) == 3 * 60


def test_a_run_records_its_slowest_box_and_keeps_the_last_five(tmp_path):
    history = tmp_path / "walls.json"
    for wall in (10.0, 20.0, 30.0, 40.0, 50.0, 60.0):
        fleet.record_wall(wall, history)
    assert fleet.load_walls(history) == [20.0, 30.0, 40.0, 50.0, 60.0]
