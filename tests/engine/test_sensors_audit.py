"""W6 lane S3: the audit hook, its two sensors' minimisation and its lifecycle (plan W6 scenarios 1, 2, 4, 5, 7).

An audit hook cannot be removed, so anything that installs the real one runs in a child interpreter; in-process tests
drive a hub whose ``add_hook`` is a recorder, calling the captured dispatcher by hand.
"""

from __future__ import annotations

import gc
import json
import os
import subprocess
import sys
import textwrap
import weakref
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.sensors.audit import AuditHub
from sharpit.engine.sensors.files import FilesSensor
from sharpit.engine.sensors.lane import SensorLane, build_lane
from sharpit.engine.sensors.processes import ProcessesSensor
from sharpit.settings_registry import JOURNAL_SOURCES

Dispatcher = Callable[[str, tuple[Any, ...]], None]
CANARY = "CANARY-s3cr3t-7f3a9c"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1rwW0gpaXHV3-ABC"


class Recorder:
    """A ``sys.addaudithook`` stand-in: remembers the dispatcher it was given."""

    def __init__(self) -> None:
        self.hooks: list[Dispatcher] = []

    def __call__(self, hook: Dispatcher) -> None:
        self.hooks.append(hook)

    def fire(self, event: str, *args: Any) -> None:
        for hook in self.hooks:
            hook(event, args)


class Sink:
    """A journal stand-in: a plain object, so it can be weakly referenced and made to fail."""

    def __init__(self, fail: Exception | BaseException | None = None) -> None:
        self.rows: list[Mapping[str, object]] = []
        self.fail = fail

    def offer(self, event: Mapping[str, object]) -> bool:
        if self.fail is not None:
            raise self.fail
        self.rows.append(event)
        return True

    def records(self, source: str) -> tuple[dict[str, object], ...]:
        return tuple(dict(row) for row in self.rows if row.get("source") == source)


class Probe:
    """A sensor that records which events it saw and what it was told to do."""

    name = "probe"
    events: tuple[str, ...] = ("probe.event",)

    def __init__(self, raises: BaseException | None = None) -> None:
        self.calls = 0
        self.raises = raises

    def record(self, event: str, args: tuple[Any, ...]) -> tuple[Mapping[str, object], ...]:
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return ({"source": "probe", "kind": event},)


def _child(code: str, tmp_path: Path) -> dict[str, Any]:
    done = subprocess.run(
        [sys.executable, "-I", "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=tmp_path,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert done.stderr == ""  # the hook never prints
    return json.loads(done.stdout.strip().splitlines()[-1])


# --- scenario 1: raises / re-enters / logs, in a child interpreter -------------------------------------------------


def test_the_real_hook_never_raises_reenters_or_logs(tmp_path: Path) -> None:
    out = _child(
        """
        import json, logging, sys
        from sharpit.engine.sensors.audit import AuditHub

        logged = []
        class Capture(logging.Handler):
            def emit(self, record): logged.append(record.getMessage())
        logging.getLogger().addHandler(Capture())
        logging.getLogger().setLevel(1)

        class Sink:
            def __init__(self, fail): self.fail, self.offers = fail, 0
            def offer(self, event):
                self.offers += 1
                sys.audit("probe.event")  # a re-entrant audit event from inside the offer
                if self.fail: raise self.fail
                return True

        class Sensor:
            name, events = "probe", ("probe.event",)
            def __init__(self): self.calls = 0
            def record(self, event, args):
                self.calls += 1
                return ({"source": "probe"},)

        class Exploding:
            name, events = "exploding", ("probe.event",)
            def record(self, event, args): raise KeyboardInterrupt

        hub = AuditHub()
        sink, failing = Sink(None), Sink(RuntimeError("sink failed"))
        sensor = Sensor()
        hub.enable(Exploding(), failing)
        hub.enable(sensor, sink)
        hub.enable(Sensor(), failing)
        sys.audit("probe.event")  # would raise if the hook let anything out
        print(json.dumps({"logged": logged, "offers": sink.offers, "calls": sensor.calls, "failing": failing.offers}))
        """,
        tmp_path,
    )
    assert out["logged"] == []
    assert out["offers"] == 1  # the nested event inside the offer was not dispatched again
    assert out["calls"] == 1
    assert out["failing"] == 1  # a failing sink and an exploding sensor stop nothing else


def test_the_real_hook_is_installed_once_across_enable_release_enable(tmp_path: Path) -> None:
    out = _child(
        """
        import json, sys
        from sharpit.engine.sensors.audit import AuditHub

        added = []
        real = sys.addaudithook
        def counting(hook):
            added.append(hook)
            real(hook)
        sys.addaudithook = counting

        class Sink:
            def __init__(self): self.rows = []
            def offer(self, event): self.rows.append(event); return True
        class Sensor:
            name, events = "probe", ("probe.event",)
            def record(self, event, args): return ({"source": "probe"},)

        hub = AuditHub()
        sink, sensor = Sink(), Sensor()
        before = len(added)
        hub.enable(sensor, sink)
        hub.enable(sensor, sink)
        sys.audit("probe.event")
        hub.release()
        sys.audit("probe.event")
        hub.enable(sensor, sink)
        sys.audit("probe.event")
        hub.release()
        print(json.dumps({"installs": len(added) - before, "rows": len(sink.rows), "installed": hub.installed}))
        """,
        tmp_path,
    )
    assert out == {"installs": 1, "rows": 2, "installed": True}  # inert while released, one dispatcher throughout


# --- scenario 5: lifecycle, in process through a recording add_hook ------------------------------------------------


def test_a_hub_installs_nothing_until_a_sensor_is_enabled() -> None:
    recorder = Recorder()
    hub = AuditHub(add_hook=recorder)
    assert recorder.hooks == []
    assert hub.installed is False
    hub.enable(Probe(), Sink())
    assert len(recorder.hooks) == 1
    assert hub.installed is True


def test_release_leaves_the_one_hook_inert_and_reenable_reuses_it() -> None:
    recorder, sink, probe = Recorder(), Sink(), Probe()
    hub = AuditHub(add_hook=recorder)
    hub.enable(probe, sink)
    hub.enable(probe, sink)
    recorder.fire("probe.event")
    hub.release()
    recorder.fire("probe.event")
    hub.enable(probe, sink)
    recorder.fire("probe.event")
    assert len(recorder.hooks) == 1
    assert probe.calls == 2
    assert len(sink.rows) == 2


def test_two_contexts_sharing_the_hub_each_keep_their_own_sensor() -> None:
    recorder, hub = Recorder(), None
    hub = AuditHub(add_hook=recorder)
    first, second = (Sink(), Probe()), (Sink(), Probe())
    hub.enable(first[1], first[0])
    hub.enable(second[1], second[0])
    recorder.fire("probe.event")
    hub.release(first[1])
    recorder.fire("probe.event")
    assert (len(first[0].rows), len(second[0].rows)) == (1, 2)


# --- scenario 7: a suspended sensor costs a flag test, not a minimisation ------------------------------------------


def test_a_disabled_sensor_is_not_minimised_and_resumes() -> None:
    recorder, sink, probe = Recorder(), Sink(), Probe()
    hub = AuditHub(add_hook=recorder)
    hub.enable(probe, sink)
    hub.disable(probe)
    recorder.fire("probe.event")
    assert probe.calls == 0
    assert hub.is_on(probe) is False
    hub.enable(probe, sink)
    recorder.fire("probe.event")
    assert probe.calls == 1


def test_suspending_the_capture_registry_switches_the_lane_off_at_the_hook() -> None:
    recorder, journal = Recorder(), RuntimeJournal(sources=["processes"])
    lane = build_lane(("processes",), journal, lambda p: p, audit=AuditHub(add_hook=recorder))
    assert lane is not None
    lane.attach()
    recorder.fire("os.system", "echo hi")
    for hook in lane.hooks():
        hook.suspend()
    recorder.fire("os.system", "echo hi")
    assert len(journal.records("processes")) == 1
    for hook in lane.hooks():
        hook.resume()
    recorder.fire("os.system", "echo hi")
    assert len(journal.records("processes")) == 2


def test_a_lane_without_a_configured_sensor_or_a_journal_does_not_exist() -> None:
    journal = RuntimeJournal()
    assert build_lane((), journal, lambda p: p) is None
    assert (
        build_lane(("network", "inventory"), journal, lambda p: p) is None
    )  # accepted ids this version does not build
    assert build_lane(("files",), None, lambda p: p) is None


def test_detach_unbinds_and_the_next_attach_rebinds() -> None:
    recorder, journal = Recorder(), RuntimeJournal(sources=["files"])
    lane = build_lane(("files",), journal, lambda p: p, audit=AuditHub(add_hook=recorder))
    assert lane is not None
    lane.attach()
    lane.detach()
    recorder.fire("os.remove", "x.txt")
    assert journal.records("files") == ()
    lane.attach()
    recorder.fire("os.remove", "x.txt")
    assert len(journal.records("files")) == 1


def test_the_switch_action_turns_files_off_and_on_and_refuses_the_rest() -> None:
    recorder, journal = Recorder(), RuntimeJournal(sources=["files", "processes"])
    lane = build_lane(("files", "processes"), journal, lambda p: p, audit=AuditHub(add_hook=recorder))
    assert isinstance(lane, SensorLane)
    lane.attach()
    assert lane.switch("files", False) is True
    recorder.fire("os.remove", "x.txt")
    assert journal.records("files") == ()
    assert lane.switch("files", True) is True
    recorder.fire("os.remove", "x.txt")
    assert len(journal.records("files")) == 1
    assert lane.switch("processes", False) is False  # BootUI keeps the processes sensor always on
    assert lane.switch("threads", True) is False  # a sensor this version does not build


def test_the_hub_holds_no_strong_reference_to_a_sink() -> None:
    recorder, sink = Recorder(), Sink()
    hub = AuditHub(add_hook=recorder)
    probe = Probe()
    hub.enable(probe, sink)
    alive = weakref.ref(sink)
    del sink
    gc.collect()
    assert alive() is None
    recorder.fire("probe.event")  # a dead sink is skipped, never raised
    assert hub.is_on(probe) is False


# --- scenario 2: the minimisation table, with canary seeds ---------------------------------------------------------


def _processes(event: str, *args: Any) -> list[Mapping[str, object]]:
    return list(ProcessesSensor().record(event, args))


@pytest.mark.parametrize(
    ("event", "args", "target"),
    [
        ("subprocess.Popen", ("/usr/bin/git", ["git", "push", CANARY], "/work", {"TOKEN": CANARY}), "git"),
        ("subprocess.Popen", (None, ["C:\\Tools\\curl.exe", "-H", CANARY], None, None), "curl.exe"),
        ("subprocess.Popen", (None, f'"C:\\Program Files\\x\\tool.exe" --key {CANARY}', None, None), "tool.exe"),
        ("os.system", (f"TOKEN={CANARY} PASS='{CANARY}' backup --secret {CANARY}",), "backup"),
        ("os.system", ("FOO=bar",), None),
        ("os.system", (f'"prog --password {CANARY}',), "(unknown)"),  # an unclosed quote: BootUI's unknown marker
        ("os.system", (f"	  tool	--password {CANARY}",), "tool"),
        ("os.system", (f"cmd /c tool --password {CANARY}",), "cmd"),
        ("os.system", (f'"C:\\Program Files\\x y\\tool.exe" --password {CANARY}',), "tool.exe"),
        ("subprocess.Popen", (f"prog {CANARY}", ["x"], None, None), "prog"),  # POSIX: executable="prog <secret>"
        ("subprocess.Popen", (f"  prog	{CANARY}", ["x"], None, None), "prog"),
        ("subprocess.Popen", (None, [f"prog {CANARY}", "a"], None, None), "prog"),
        (
            "subprocess.Popen",
            (f"/usr/bin/my tool {CANARY}", ["x"], None, None),
            "my",
        ),  # the file name stops at its first blank too
        ("os.exec", (b"/bin/sh", [b"sh", CANARY.encode()], {"A": CANARY}), "sh"),
        ("os.spawn", (0, "/usr/bin/ls", ["ls", CANARY], {}), "ls"),
        ("os.posix_spawn", ("/usr/bin/id", ["id", CANARY], {}), "id"),
    ],
    ids=[
        "popen",
        "popen-windows",
        "popen-string",
        "system-assignments",
        "system-only-assignment",
        "system-unclosed-quote",
        "system-tab-and-leading-blanks",
        "system-cmd-c",
        "system-quoted-path-with-spaces",
        "popen-executable-with-args",
        "popen-executable-tab",
        "popen-argv0-with-args",
        "popen-path-name-with-blanks",
        "exec",
        "spawn",
        "pspawn",
    ],
)
def test_the_processes_sensor_keeps_the_file_name_and_nothing_else(
    event: str, args: tuple[Any, ...], target: str | None
) -> None:
    rows = _processes(event, *args)
    assert [row.get("target") for row in rows] == ([target] if target else [])
    assert CANARY not in json.dumps(rows)
    assert all(set(row) == {"source", "kind", "target"} for row in rows)


def test_the_processes_sensor_survives_odd_arguments() -> None:
    assert _processes("subprocess.Popen", None, [], None, None) == []
    assert _processes("subprocess.Popen", 7, 7, None, None) == []
    assert isinstance(_processes("os.system", b"\xff\xfe"), list)  # undecodable bytes never raise


def _files(**options: Any) -> FilesSensor:
    base = {"cwd": "/work/app", "home": "/home/ann", "tmp": "/tmp"}  # noqa: S108 - a pattern under test, never opened
    return FilesSensor(**{**base, **options})


@pytest.mark.parametrize(
    ("event", "args", "kind", "target", "location"),
    [
        (
            "open",
            ("/work/app/reports/report-42.csv", "w", 0),
            "write",
            "./reports/report-{n}.csv",
            "working-directory",
        ),
        ("open", ("reports/a.csv", "rb", 0), "read", "./reports/a.csv", "working-directory"),
        ("open", ("/home/ann/.config/app.toml", "r", 0), "read", "~/.config/app.toml", "home"),
        (
            "open",
            ("/tmp/work-3f2a9c1b77.tmp", None, os.O_WRONLY),
            "write",
            "$TMPDIR/work-{hex}.tmp",
            "temporary-directory",
        ),
        ("open", ("/etc/hosts", "r", 0), "read", "/etc/hosts", "system"),
        ("open", ("/data/9b2c1d3e-1111-2222-3333-444455556666/x", "r", 0), "read", "/data/{uuid}/x", "elsewhere"),
        ("os.remove", ("/work/app/old.log", None), "delete", "./old.log", "working-directory"),
    ],
)
def test_the_files_sensor_collapses_a_path_to_a_pattern(
    event: str, args: tuple[Any, ...], kind: str, target: str, location: str
) -> None:
    rows = _files().record(event, args)
    assert [(row["kind"], row["target"], row["location"]) for row in rows] == [(kind, target, location)]
    assert all(set(row) == {"source", "kind", "target", "origin", "location"} for row in rows)


@pytest.mark.parametrize(
    ("event", "first", "second"),
    [("os.rename", "move from", "move to"), ("shutil.copyfile", "copy from", "copy to")],
)
def test_a_move_or_copy_records_its_source_and_its_destination(event: str, first: str, second: str) -> None:
    rows = _files().record(event, ("/work/app/a.txt", "/work/app/b.txt"))
    assert [(row["kind"], row["target"]) for row in rows] == [(first, "./a.txt"), (second, "./b.txt")]


def test_the_files_sensor_masks_a_secret_segment_and_never_shows_content_or_descriptors() -> None:
    from sharpit.engine.masking import Exposure, Masker

    masker = Masker(Exposure.MASKED, True)
    sensor = _files(mask_path=masker.mask_path)
    rows = sensor.record("open", (f"/work/app/reset/{JWT}/token.txt", "r", 0))
    assert [row["target"] for row in rows] == ["./reset/******/token.txt"]
    assert JWT not in json.dumps(rows)
    assert list(sensor.record("open", (3, "r", 0))) == []  # a file descriptor names no file


def test_the_files_sensor_leaves_out_imports_and_sharpits_own_state(tmp_path: Path) -> None:
    own = tmp_path / "state"
    sensor = FilesSensor(own=[str(own)], cwd=str(tmp_path), home=str(tmp_path), tmp=str(tmp_path))
    assert list(sensor.record("open", (os.path.join(sys.prefix, "lib", "x.py"), "rb", 0))) == []
    assert list(sensor.record("open", (str(own / "ledger.db"), "rb", 0))) == []
    assert sensor.ignored == 2
    assert len(sensor.record("open", (str(tmp_path / "app.cfg"), "rb", 0))) == 1


def test_the_path_cache_never_grows_past_its_bound() -> None:
    from sharpit.engine.sensors import files

    sensor = _files()
    largest = 0
    for i in range(files._SEEN * 2 + 10):  # pyright: ignore[reportPrivateUsage]
        sensor.record("open", (f"/work/app/data/file-{i}.csv", "r", 0))
        largest = max(largest, len(sensor._seen))  # pyright: ignore[reportPrivateUsage]
    assert largest <= files._SEEN  # pyright: ignore[reportPrivateUsage]


def test_the_announced_copy_paths_never_grow_past_their_bound() -> None:
    from sharpit.engine.sensors import files

    sensor = _files()
    largest = 0
    for i in range(files._PENDING * 2 + 10):  # pyright: ignore[reportPrivateUsage]
        sensor.record("shutil.copyfile", (f"/work/a-{i}.csv", f"/work/b-{i}.csv"))
        largest = max(largest, len(sensor._pending))  # pyright: ignore[reportPrivateUsage]
    assert largest <= files._PENDING  # pyright: ignore[reportPrivateUsage]


def test_a_dispatcher_whose_thread_state_is_gone_still_never_raises() -> None:
    class Gone:
        def __getattr__(self, name: str) -> object:
            raise RuntimeError(name)

    recorder = Recorder()
    hub = AuditHub(add_hook=recorder)
    hub.enable(ProcessesSensor(), RuntimeJournal(sources=JOURNAL_SOURCES))
    hub._busy = Gone()  # pyright: ignore[reportPrivateUsage, reportAttributeAccessIssue]
    raised: BaseException | None = None
    try:
        recorder.fire("os.system", "prog")  # interpreter shutdown can leave the thread-local unusable
    except BaseException as error:  # noqa: BLE001 - the test asserts the hook let nothing out
        raised = error
    assert raised is None


def test_a_cache_cleared_by_another_thread_mid_lookup_still_records_the_row() -> None:
    class ClearedMidLookup(dict[str, Any]):
        """Another thread clears the cache between a membership test and the read that follows it."""

        def __contains__(self, key: object) -> bool:
            self.clear()
            return True

    sensor, sink, recorder = _files(), Sink(), Recorder()
    sensor._seen = ClearedMidLookup()  # pyright: ignore[reportPrivateUsage]
    AuditHub(add_hook=recorder).enable(sensor, sink)
    recorder.fire("open", "/work/app/a.txt", "r", 0)  # the hook swallows whatever the sensor raises: a lost row
    assert [row["target"] for row in sink.records("files")] == ["./a.txt"]


def test_a_failed_copy_does_not_hide_the_applications_next_open(tmp_path: Path) -> None:
    out = _child(
        """
        import json, os, shutil
        from sharpit.engine.sensors.audit import AuditHub
        from sharpit.engine.sensors.files import FilesSensor

        class Sink:
            def __init__(self): self.rows = []
            def offer(self, event): self.rows.append(event); return True

        here = os.getcwd()
        sink, hub = Sink(), AuditHub()
        hub.enable(FilesSensor(cwd=here, home="/nohome", tmp="/notmp"), sink)
        with open("a.txt", "w") as f:
            f.write("x")
        sink.rows.clear()
        shutil.copyfile("a.txt", "b.txt")  # its own two opens are the copy's: two rows, not four
        try:
            shutil.copyfile("a.txt", "a.txt")  # SameFileError after the audit event, before any open
        except shutil.SameFileError:
            pass
        with open("a.txt") as f:  # the application's own read, after the failed copy
            f.read()
        hub.release()
        rows = [(r["kind"], r["target"]) for r in sink.rows if r["target"] in ("./a.txt", "./b.txt")]
        print(json.dumps(rows))
        """,
        tmp_path,
    )
    assert out == [
        ["copy from", "./a.txt"],
        ["copy to", "./b.txt"],
        ["copy from", "./a.txt"],
        ["copy to", "./a.txt"],
        ["read", "./a.txt"],
    ]


# --- scenario 4: the journal takes both sensors' sources -----------------------------------------------------------


@pytest.mark.parametrize("source", ["processes", "files"])
def test_the_journal_accepts_each_sensors_source(source: str) -> None:
    assert source in JOURNAL_SOURCES
    journal = RuntimeJournal(sources=JOURNAL_SOURCES)
    assert journal.offer({"source": source, "kind": "x", "target": "t"}) is True
    assert len(journal.records(source)) == 1
    assert journal.status()["dropped"] == {}


def test_a_canary_in_argv_env_and_shell_arguments_never_reaches_the_journal() -> None:
    journal = RuntimeJournal(sources=JOURNAL_SOURCES)
    recorder = Recorder()
    lane = build_lane(("processes", "files"), journal, lambda p: p, audit=AuditHub(add_hook=recorder))
    assert lane is not None
    lane.attach()
    recorder.fire("subprocess.Popen", "/bin/tool", ["tool", CANARY], CANARY, {"K": CANARY})
    recorder.fire("os.system", f"K={CANARY} tool {CANARY}")
    recorder.fire("open", "/work/data.bin", "rb", 0)
    assert [row["target"] for row in journal.records("processes")] == ["tool", "tool"]
    assert CANARY not in json.dumps([journal.records("processes"), journal.records("files"), journal.status()])


@pytest.mark.parametrize(
    ("event", "args"),
    [
        ("os.system", (f'"prog --password {CANARY}',)),
        ("os.system", (f"cmd /c prog --password {CANARY}",)),
        ("subprocess.Popen", (f"prog {CANARY}", ["x"], None, None)),
        ("subprocess.Popen", (None, [f"prog {CANARY}"], None, None)),
        ("os.exec", (f"/bin/prog {CANARY}", [f"prog {CANARY}"], {})),
    ],
)
def test_a_space_separated_secret_never_reaches_the_journal_even_masked(event: str, args: tuple[Any, ...]) -> None:
    from sharpit.engine.masking import Exposure, Masker

    masker = Masker(Exposure.MASKED, True)
    journal = RuntimeJournal(sources=JOURNAL_SOURCES)
    recorder = Recorder()
    lane = build_lane(("processes",), journal, masker.mask_path, audit=AuditHub(add_hook=recorder))
    assert lane is not None
    lane.attach()
    recorder.fire(event, *args)
    assert len(journal.records("processes")) == 1
    assert CANARY not in json.dumps(journal.records("processes"))


# Each case leaked a fragment through round 2's cut rules: the target is the program's file name or ``(unknown)``.
FRAGMENT_CASES = [
    ("os.system", (f'"/opt/tool --token-file /run/secrets/{CANARY}',), "(unknown)"),
    ("subprocess.Popen", (f"/usr/bin/curl https://api.example/key={CANARY}", ["x"], None, None), "curl"),
    ("subprocess.Popen", (None, [f"/bin/x /tmp/{CANARY}"], None, None), "x"),
    ("os.system", (f"A=s3cr\\ {CANARY} prog",), "prog"),
    ("os.system", (f'A="a \\"b {CANARY}" prog',), "prog"),
    ("os.system", (f"A=$(cat /run/{CANARY} key) prog",), "prog"),
    ("os.system", (f"A='x {CANARY} prog",), "(unknown)"),
    ("os.system", (f'"C:\\Program Files\\x\\y.exe" --password {CANARY}',), "y.exe"),
    ("subprocess.Popen", (None, f'"C:\\Program Files\\x\\y.exe" --password {CANARY}', None, None), "y.exe"),
    # an unquoted path with blanks: the first word only, never the words after it
    ("subprocess.Popen", (f"C:\\Program Files\\x\\y.exe --password {CANARY}", ["x"], None, None), "Program"),
    ("subprocess.Popen", (f"TOKEN={CANARY} prog", ["x"], None, None), "prog"),
    ("os.system", (f'cmd /c "prog {CANARY}"',), "cmd"),
    ("os.system", (f"env A={CANARY} prog",), "env"),
    ("os.system", (f"\tprog\t--password\t{CANARY}",), "prog"),
    # round 4: a shell metacharacter glued to the program ends the word; one that starts it is not a program
    ("os.system", (f"prog>/tmp/{CANARY}.log",), "prog"),
    ("os.system", (f"prog;{CANARY}",), "prog"),
    ("os.system", (f"prog|{CANARY}",), "prog"),
    ("os.system", (f"prog#{CANARY}",), "prog"),
    ("os.system", (f"prog&{CANARY}",), "prog"),
    ("os.system", (f"prog<{CANARY}",), "prog"),
    ("os.system", (f"`{CANARY}` prog",), "(unknown)"),
    ("os.system", (f"$(cat /etc/{CANARY}) x",), "(unknown)"),
    ("os.system", (f"${{{CANARY}}} x",), "(unknown)"),
    ("os.system", (f"(prog {CANARY})",), "(unknown)"),
    ("os.system", (f"C:\dir\ {CANARY}",), "(unknown)"),  # cmd.exe: a trailing backslash is not an escape
]


@pytest.mark.parametrize("exposure", ["MASKED", "FULL"])
@pytest.mark.parametrize(
    ("event", "args", "target"),
    FRAGMENT_CASES,
    ids=[
        "unclosed-quote-path",
        "popen-url-with-slash",
        "argv0-path-with-args",
        "escaped-blank-value",
        "escaped-quote-value",
        "command-substitution-value",
        "unclosed-quote-value",
        "system-quoted-windows-path",
        "popen-quoted-windows-path",
        "popen-unquoted-windows-path",
        "popen-assignment-executable",
        "cmd-c",
        "env",
        "tabs",
        "redirect-glued",
        "semicolon-glued",
        "pipe-glued",
        "hash-glued",
        "ampersand-glued",
        "less-than-glued",
        "backtick-first",
        "command-substitution-first",
        "parameter-expansion-first",
        "subshell-first",
        "windows-trailing-backslash",
    ],
)
def test_no_argument_or_value_fragment_reaches_the_journal(
    exposure: str, event: str, args: tuple[Any, ...], target: str
) -> None:
    from sharpit.engine.masking import Exposure, Masker

    journal = RuntimeJournal(sources=JOURNAL_SOURCES)
    recorder = Recorder()
    masker = Masker(Exposure(exposure), True)
    lane = build_lane(("processes",), journal, masker.mask_path, audit=AuditHub(add_hook=recorder))
    assert lane is not None
    lane.attach()
    recorder.fire(event, *args)
    assert [row["target"] for row in journal.records("processes")] == [target]
    assert CANARY not in json.dumps(journal.records("processes"))


# --- the files sensor's patterns, as BootUI's ``SideEffects.pattern`` and ``collapse`` -----------------------------


@pytest.mark.parametrize(
    ("path", "pattern"),
    [
        ("/home/bob/secrets.txt", "/home/*/secrets.txt"),
        ("/Users/carol/Documents/x.pdf", "/Users/*/Documents/x.pdf"),
        ("D:\\Users\\dave\\notes.txt", "D:/Users/*/notes.txt"),
        ("\\\\srv\\Users\\erin\\notes.txt", "/srv/Users/*/notes.txt"),
        ("\\\\?\\D:\\Users\\frank\\notes.txt", "/?/D:/Users/*/notes.txt"),
        ("/var/home/grace/notes.txt", "/var/home/*/notes.txt"),
        ("/export/home/heidi/notes.txt", "/export/home/*/notes.txt"),
        ("/srv/site/home/index.html", "/srv/site/home/index.html"),
    ],
)
def test_another_users_home_never_keeps_their_name(path: str, pattern: str) -> None:
    # ported: SideEffectPathsTests.anotherUsersHomeNeverKeepsTheirName
    rows = _files(cwd="/srv/app", home="/home/ann", tmp="/tmp").record("open", (path, "r", 0))  # noqa: S108
    assert [row["target"] for row in rows] == [pattern]


@pytest.mark.parametrize(
    ("name", "collapsed"),
    [
        ("550e8400-e29b-41d4-a716-446655440000.json", "{uuid}.json"),
        ("0123abcdef9.bin", "{hex}.bin"),
        ("sk_live_" + "abc123def456ghi789jkl.txt", "sk_live_{id}.txt"),  # split: no secret-shaped literal
        ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig", "{token}"),
        ("release-17.txt", "release-{n}.txt"),
        ("name.txt", "name.txt"),
        ("aB3dE5fG7hJ9kL1m.key", "{id}.key"),
        ("report2026q.csv", "report{n}q.csv"),
        ("QwErTyUiOpAsDfGhJkLzXcVbNm.txt", "{id}.txt"),
        ("applicationconfigurationfile.txt", "applicationconfigurationfile.txt"),
        ("deadbeefcafe.txt", "deadbeefcafe.txt"),  # eight hex letters and no digit: a word, kept
    ],
)
def test_ids_collapse_so_random_names_cannot_fill_the_table(name: str, collapsed: str) -> None:
    # ported: SideEffectPathsTests.idsCollapseSoRandomNamesCannotFillTheTable
    rows = _files(cwd="/srv/app").record("open", (f"/srv/app/k/{name}", "r", 0))
    assert [row["target"] for row in rows] == [f"./k/{collapsed}"]


def test_a_pattern_is_cut_at_two_hundred_characters() -> None:
    rows = _files(cwd="/srv/app").record("open", ("/srv/app/" + "d/" * 150 + "x.txt", "r", 0))
    assert len(str(rows[0]["target"])) == 200
