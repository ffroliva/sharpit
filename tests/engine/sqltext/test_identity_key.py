import multiprocessing
import os
import shutil
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from sharpit.engine.sqltext import identity
from sharpit.engine.sqltext.identity import fingerprint, load_key
from sharpit.settings import load_settings

WORKERS = 8
ROUNDS = 200


def _worker_key(state_dir: str) -> bytes | None:
    return load_key(Path(state_dir), create=True)


def test_sqlite_identity_survives_a_new_process(tmp_path: Path) -> None:
    key = load_key(tmp_path, create=True)
    assert key is not None
    expected = fingerprint("select * from users", key)
    code = (
        "from pathlib import Path; from sharpit.engine.sqltext.identity import load_key, fingerprint; "
        f"print(fingerprint('select * from users', load_key(Path({str(tmp_path)!r}), create=False)))"
    )
    actual = subprocess.check_output([sys.executable, "-c", code], text=True).strip()
    assert actual == expected


def test_two_workers_create_one_key(tmp_path: Path) -> None:
    with ProcessPoolExecutor(max_workers=2) as pool:
        keys = list(pool.map(_worker_key, [str(tmp_path)] * 2))
    assert keys[0] == keys[1]


_start_line: Any = None


def _share_start_line(barrier: Any) -> None:
    global _start_line  # noqa: PLW0603 - a pool initializer has no other way to hand a worker its barrier
    _start_line = barrier


def _racing_key(state_dir: str) -> bytes | None:
    _start_line.wait(timeout=30)
    return load_key(Path(state_dir), create=True)


@pytest.mark.parametrize("left_behind", [None, b"", b"short"], ids=["fresh", "crashed_empty", "crashed_short"])
def test_eight_workers_at_a_barrier_share_one_key(tmp_path: Path, left_behind: bytes | None) -> None:
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(WORKERS)
    with ProcessPoolExecutor(WORKERS, context, _share_start_line, (barrier,)) as pool:
        for race in range(ROUNDS):
            state_dir = tmp_path / str(race)
            if left_behind is not None:
                state_dir.mkdir()
                (state_dir / "identity.key").write_bytes(left_behind)
            keys = [pool.submit(_racing_key, str(state_dir)) for _ in range(WORKERS)]
            got = {key.result(timeout=60) for key in keys}
            assert None not in got, f"a worker went keyless in round {race}"
            assert len(got) == 1, f"round {race} made {len(got)} keys"
            assert (state_dir / "identity.key").read_bytes() in got


def test_a_crash_before_the_key_lands_leaves_nothing_to_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def crash(*_args: object) -> None:
        raise OSError("disk gone")

    monkeypatch.setattr(identity.os, "replace", crash)
    monkeypatch.setattr(identity, "WAIT_SECONDS", 0, raising=False)
    assert load_key(tmp_path, create=True) is None
    assert not (tmp_path / "identity.key").exists()
    assert [path.name for path in tmp_path.iterdir() if path.name.endswith(".tmp")] == []


def test_a_creator_replaces_a_file_a_crash_left_short(tmp_path: Path) -> None:
    (tmp_path / "identity.key").write_bytes(b"cut")
    key = load_key(tmp_path, create=True)
    assert key is not None
    assert len(key) == 32
    assert (tmp_path / "identity.key").read_bytes() == key


def test_a_reader_refuses_a_bad_file_and_leaves_it(tmp_path: Path) -> None:
    (tmp_path / "identity.key").write_bytes(b"cut")
    assert load_key(tmp_path, create=False) is None
    assert (tmp_path / "identity.key").read_bytes() == b"cut"


def test_a_creator_retries_a_transient_permission_error_on_the_first_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = b"k" * 32
    (tmp_path / "identity.key").write_bytes(key)
    real_read, reads = identity._read, 0

    def transient_error(path: Path) -> bytes | None:
        nonlocal reads
        reads += 1
        if reads == 1:
            raise PermissionError("rename in progress")
        return real_read(path)

    monkeypatch.setattr(identity, "_read", transient_error)

    assert load_key(tmp_path, create=True) == key
    assert reads >= 2


def test_a_key_longer_than_a_key_is_bad(tmp_path: Path) -> None:
    (tmp_path / "identity.key").write_bytes(b"k" * 33)
    assert load_key(tmp_path, create=False) is None


def test_a_good_key_is_read_and_ignored(tmp_path: Path) -> None:
    (tmp_path / "identity.key").write_bytes(b"k" * 32)
    assert load_key(tmp_path, create=True) == b"k" * 32
    assert sorted(path.name for path in tmp_path.iterdir()) == [".gitignore", "identity.key", "identity.key.lock"]
    assert "identity.key" in (tmp_path / ".gitignore").read_text().splitlines()


@pytest.mark.skipif(os.name == "nt", reason="Windows does not enforce POSIX read-only file modes")
def test_read_only_gitignore_with_all_rules_keeps_the_existing_key_without_a_lock(tmp_path: Path) -> None:
    ignore = tmp_path / ".gitignore"
    ignore.write_bytes(b"identity.key\nidentity.key.lock\nidentity.key.*\n")
    ignore.chmod(0o444)
    key = b"k" * 32
    (tmp_path / "identity.key").write_bytes(key)

    assert load_key(tmp_path, create=True) == key
    assert not (tmp_path / "identity.key.lock").exists()


@pytest.mark.skipif(os.name == "nt", reason="Windows does not enforce POSIX directory modes")
def test_read_only_directory_with_old_rules_keeps_an_ignored_existing_key(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_bytes(b"identity.key\nidentity.key.*\n")
    key = b"k" * 32
    (tmp_path / "identity.key").write_bytes(key)
    tmp_path.chmod(0o555)
    try:
        assert load_key(tmp_path, create=True) == key
        assert not (tmp_path / "identity.key.lock").exists()
    finally:
        tmp_path.chmod(0o755)


@pytest.mark.parametrize("content", [b"# caf\xe9\n", "# sharpit\n".encode("utf-16")], ids=["latin1", "utf16"])
def test_an_existing_gitignore_with_another_encoding_keeps_the_key(tmp_path: Path, content: bytes) -> None:
    (tmp_path / ".gitignore").write_bytes(content)
    key = load_key(tmp_path, create=True)
    assert key is not None
    assert (tmp_path / "identity.key").read_bytes() == key


def test_a_gitignore_symlink_is_refused_without_writing_through_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "outside"
    target.write_bytes(b"mine\n")
    ignore = tmp_path / ".gitignore"
    ignore.write_bytes(b"mine\n")
    real_is_symlink = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == ignore or real_is_symlink(path))
    assert load_key(tmp_path, create=True) is None
    assert target.read_bytes() == b"mine\n"
    assert not (tmp_path / "identity.key").exists()
    assert not (tmp_path / "identity.key.lock").exists()


def test_the_key_is_created_owner_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Asked of ``os.open``, so a platform with no POSIX modes still answers (the stat test above says it for POSIX)."""
    real, modes = os.open, {}

    def spy(path: Any, flags: int, mode: int = 0o777, **kwargs: Any) -> int:
        modes[Path(path).name] = mode
        return real(path, flags, mode, **kwargs)

    monkeypatch.setattr(identity.os, "open", spy)
    load_key(tmp_path, create=True)
    written = [name for name in modes if name.startswith("identity.key.") and name.endswith(".tmp")]
    assert len(written) == 1
    assert modes[written[0]] == 0o600


def test_key_and_lock_are_not_created_when_gitignore_cannot_be_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unwritable(_state_dir: Path) -> None:
        raise PermissionError("ignore is read-only")

    monkeypatch.setattr(identity, "_preflight_ignore", unwritable)

    assert load_key(tmp_path, create=True) is None
    assert not (tmp_path / "identity.key").exists()
    assert not (tmp_path / "identity.key.lock").exists()


def test_the_key_lands_beside_a_gitignore_that_names_it(tmp_path: Path) -> None:
    load_key(tmp_path, create=True)
    assert (tmp_path / ".gitignore").is_file()
    assert "identity.key" in (tmp_path / ".gitignore").read_text().splitlines()


def test_the_gitignore_is_there_before_the_key_is(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real, seen = os.replace, []

    def spy(source: Any, target: Any) -> None:
        seen.append((tmp_path / ".gitignore").is_file())
        real(source, target)

    monkeypatch.setattr(identity.os, "replace", spy)
    load_key(tmp_path, create=True)
    assert seen == [True]


@pytest.mark.parametrize("existing_key", [False, True], ids=["new-key", "existing-key"])
def test_git_add_does_not_commit_key_when_gitignore_exists(tmp_path: Path, existing_key: bool) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    state_dir = tmp_path / ".sharpit"
    state_dir.mkdir()
    ignore = state_dir / ".gitignore"
    ignore.write_text("mine\n")
    if existing_key:
        (state_dir / "identity.key").write_bytes(b"k" * 32)

    assert load_key(state_dir, create=True) is not None

    assert ignore.read_text() == "mine\nidentity.key\nidentity.key.lock\nidentity.key.*\n"
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    tracked = subprocess.run(
        ["git", "-C", str(tmp_path), "ls-files"], check=True, capture_output=True, text=True
    ).stdout.splitlines()
    assert tracked == [".sharpit/.gitignore"]


@pytest.mark.parametrize(
    "content",
    [
        b"identity.key\n!identity.key\n",
        b"identity.key\n!/identity.key\n",
        b"identity.key\n!identity*\n",
        b"identity.key\n!*\n",
        b"# comment\f identity.key\n",
        b"# comment\ridentity.key\n",
        b"# comment\x85 identity.key\n",
        b"# trailing carriage return\r",
    ],
    ids=["negate-exact", "negate-rooted", "negate-prefix", "negate-all", "formfeed", "cr", "nel", "lone-cr"],
)
@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_git_honors_the_key_ignore_rules(tmp_path: Path, content: bytes) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    state_dir = tmp_path / ".sharpit"
    state_dir.mkdir()
    ignore = state_dir / ".gitignore"
    ignore.write_bytes(content)

    assert load_key(state_dir, create=True) is not None

    ignored = subprocess.run(["git", "-C", str(tmp_path), "check-ignore", "-q", ".sharpit/identity.key"], check=False)
    assert ignored.returncode == 0
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    tracked = subprocess.run(
        ["git", "-C", str(tmp_path), "ls-files"], check=True, capture_output=True, text=True
    ).stdout.splitlines()
    assert tracked == [".sharpit/.gitignore"]


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_git_add_does_not_commit_key_when_gitignore_was_deleted(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    state_dir = tmp_path / ".sharpit"
    load_key(state_dir, create=True)
    (state_dir / ".gitignore").unlink()

    assert load_key(state_dir, create=True) is not None

    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    tracked = subprocess.run(
        ["git", "-C", str(tmp_path), "ls-files"], check=True, capture_output=True, text=True
    ).stdout.splitlines()
    assert tracked == [".sharpit/.gitignore"]


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_git_ignores_everything_beside_the_gitignore(tmp_path: Path) -> None:
    state_dir = tmp_path / ".sharpit"
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    load_key(state_dir, create=True)
    (state_dir / "identity.key.1a2b.tmp").write_bytes(b"a crash left this")  # holds a whole key
    shown = subprocess.run(
        ["git", "-C", str(tmp_path), "status", "--porcelain", "--untracked-files=all"],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    assert shown.stdout.splitlines() == ["?? .sharpit/.gitignore"]


@pytest.mark.parametrize("create", [True, False])
def test_a_nul_in_the_state_dir_gives_no_key(create: bool) -> None:
    assert load_key(Path("state\x00dir"), create=create) is None


@pytest.mark.parametrize("create", [True, False])
def test_a_symlink_at_the_key_path_is_refused(tmp_path: Path, create: bool) -> None:
    target = tmp_path / "elsewhere"
    target.write_bytes(b"k" * 32)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    try:
        (state_dir / "identity.key").symlink_to(target)
    except OSError:
        pytest.skip("this account may not make symlinks")
    assert load_key(state_dir, create=create) is None
    assert target.read_bytes() == b"k" * 32
    assert (state_dir / "identity.key").is_symlink()


@pytest.mark.parametrize("create", [True, False])
def test_a_link_is_refused_where_making_one_takes_a_privilege(
    tmp_path: Path, create: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows has no ``O_NOFOLLOW``: the lstat alone refuses there, and an unprivileged run cannot plant a link."""
    (tmp_path / "identity.key").write_bytes(b"k" * 32)
    monkeypatch.setattr(Path, "is_symlink", lambda _self: True)
    assert load_key(tmp_path, create=create) is None


def test_the_read_asks_not_to_follow_a_link_where_it_can(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "identity.key").write_bytes(b"k" * 32)
    no_follow, real, flags_seen = 1 << 30, os.open, []

    def spy(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        flags_seen.append(flags)
        return real(path, flags & ~no_follow, *args, **kwargs)

    monkeypatch.setattr(os, "O_NOFOLLOW", no_follow, raising=False)
    monkeypatch.setattr(identity.os, "open", spy)
    assert load_key(tmp_path, create=False) == b"k" * 32
    assert [flags for flags in flags_seen if flags & no_follow] != []


def test_the_lock_open_asks_not_to_follow_a_link_where_it_can(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    no_follow, real, lock_flags = 1 << 30, os.open, []

    def spy(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if Path(path).name == "identity.key.lock":
            lock_flags.append(flags)
        return real(path, flags & ~no_follow, *args, **kwargs)

    monkeypatch.setattr(os, "O_NOFOLLOW", no_follow, raising=False)
    monkeypatch.setattr(identity.os, "open", spy)
    assert load_key(tmp_path, create=True) is not None
    assert [flags for flags in lock_flags if flags & no_follow] != []


def test_gitignore_append_happens_under_the_identity_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    import sharpit.engine.sqltext.identity as identity

    (tmp_path / "identity.key").write_bytes(b"k" * 32)
    real_exclusive = identity._exclusive
    locked = False

    @contextmanager
    def tracked_lock(path: Path):
        nonlocal locked
        with real_exclusive(path):
            locked = True
            yield

    real_ignore = identity._ignore_the_key

    def checked_ignore(state_dir: Path) -> None:
        assert locked
        real_ignore(state_dir)

    monkeypatch.setattr(identity, "_exclusive", tracked_lock)
    monkeypatch.setattr(identity, "_ignore_the_key", checked_ignore)
    assert load_key(tmp_path, create=True) == b"k" * 32


def test_no_key_gives_no_identity(tmp_path: Path) -> None:
    assert fingerprint("select 'x'", None) is None
    assert load_key(tmp_path, create=False) is None


def test_key_file_is_private_on_posix(tmp_path: Path) -> None:
    key = load_key(tmp_path, create=True)
    assert key is not None
    if os.name == "posix":
        assert (tmp_path / "identity.key").stat().st_mode & 0o777 == 0o600


def test_sqlite_identity_is_keyed() -> None:
    expected = fingerprint("select * from users", b"a" * 32)
    guess = fingerprint("select * from users", b"b" * 32)
    assert guess != expected


def test_identity_takes_any_text() -> None:
    assert fingerprint("select \ud800", b"k" * 32) is not None
    assert fingerprint("select\x00x", b"k" * 32) is not None


def test_the_env_key_is_read_as_a_secret_setting() -> None:
    settings = load_settings({}, {"SHARPIT_IDENTITY_KEY": "k" * 32})
    assert settings.identity_key == "k" * 32
    assert "k" * 32 not in repr(settings.warnings)


def test_two_machines_with_one_env_key_share_identity() -> None:
    first = load_settings({}, {"SHARPIT_IDENTITY_KEY": "k" * 32})
    second = load_settings({}, {"SHARPIT_IDENTITY_KEY": "k" * 32})
    first_id = fingerprint("select * from users", first.identity_key.encode() if first.identity_key else None)
    second_id = fingerprint("select * from users", second.identity_key.encode() if second.identity_key else None)
    assert first_id == second_id


def test_an_empty_env_key_is_unset() -> None:
    settings = load_settings({}, {"SHARPIT_IDENTITY_KEY": ""})
    assert settings.identity_key is None


def test_a_short_env_key_is_rejected_without_echoing_it() -> None:
    settings = load_settings({}, {"SHARPIT_IDENTITY_KEY": "short-secret"})
    assert settings.identity_key is None
    assert all("short-secret" not in warning for warning in settings.warnings)


def test_an_unencodable_env_key_fails_safe() -> None:
    settings = load_settings({}, {"SHARPIT_IDENTITY_KEY": "\ud800" * 32})
    assert settings.identity_key is None
    assert any("SHARPIT_IDENTITY_KEY" in warning for warning in settings.warnings)
