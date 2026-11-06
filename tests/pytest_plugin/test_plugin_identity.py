import json
import os

import pytest

NPLUS_ONE = """
from sqlalchemy import ForeignKey, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Owner(Base):
    __tablename__ = "owners"
    id: Mapped[int] = mapped_column(primary_key=True)
    pets: Mapped[list["Pet"]] = relationship()


class Pet(Base):
    __tablename__ = "pets"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("owners.id"))


def test_nplus_one(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/a.db")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(Owner(id=i, pets=[Pet(id=i * 10 + j) for j in range(2)]) for i in range(1, 12))
        session.commit()
    with Session(engine) as session:
        assert sum(len(owner.pets) for owner in session.query(Owner).all()) == 22
"""


def test_a_pytest_session_creates_the_key_at_start(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> None:
    state_dir = pytester.path / "state"
    monkeypatch.setenv("SHARPIT_STATE_DIR", str(state_dir))
    pytester.makepyfile("def test_pass(): pass")
    result = pytester.runpytest("--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "-q")
    assert result.ret == 0
    assert (state_dir / "identity.key").is_file()


def test_a_session_with_no_key_warns_once_in_its_report(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = pytester.path / "a-file"
    state_dir.write_text("no directory can go here")
    monkeypatch.setenv("SHARPIT_STATE_DIR", str(state_dir))
    pytester.makepyfile("def test_pass(): pass")
    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )
    assert result.ret == 0
    warnings = json.loads((pytester.path / "report.json").read_text())["warnings"]
    identity_warnings = [warning for warning in warnings if "SQLite statement identities are unavailable" in warning]
    assert len(identity_warnings) == 1
    assert "FileExistsError" in identity_warnings[0]


def test_local_key_baseline_warns_after_sqlite_was_seen(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SHARPIT_IDENTITY_KEY", raising=False)
    monkeypatch.setenv("SHARPIT_STATE_DIR", str(pytester.path / "state"))
    (pytester.path / "baseline.json").write_text('{"schema":"sharpit-baseline/1","findings":[]}')
    pytester.makepyfile(
        "import sqlite3\ndef test_query():\n c=sqlite3.connect(':memory:')\n c.execute('select 1').fetchone()"
    )

    result = pytester.runpytest_subprocess(
        "--sharpit",
        "--sharpit-no-advisors",
        "--sharpit-allow-unknown",
        "--sharpit-baseline=baseline.json",
        "--sharpit-report=report.json",
        "-q",
    )

    assert result.ret == 0
    report = json.loads((pytester.path / "report.json").read_text())
    assert any("local identity key" in warning and "SHARPIT_IDENTITY_KEY" in warning for warning in report["warnings"])


@pytest.mark.parametrize("broken_state", ["file", "read-only", "unreadable-config"])
def test_broken_state_still_writes_a_report_with_a_reason(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, broken_state: str
) -> None:
    state_dir = pytester.path / "state"
    if broken_state == "file":
        state_dir.write_text("not a directory")
    else:
        state_dir.mkdir()
        if broken_state == "read-only":
            if os.name == "nt":
                pytest.skip("Windows chmod does not make a directory read-only")
            state_dir.chmod(0o555)
        else:
            if os.name == "nt":
                pytest.skip("Windows chmod does not make a file unreadable")
            config = state_dir / "sharpit.yml"
            config.write_text("dismissedRules:\n")
            config.chmod(0)
    monkeypatch.setenv("SHARPIT_STATE_DIR", str(state_dir))
    pytester.makepyfile("def test_pass(): pass")

    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )

    assert result.ret == 0
    report = json.loads((pytester.path / "report.json").read_text())
    if broken_state == "unreadable-config":
        assert any(source["name"] == "dismissals" and not source["attached"] for source in report["sources"])
    else:
        assert any("SQLite statement identities are unavailable" in warning for warning in report["warnings"])


def test_a_repeating_group_on_sqlite_keeps_its_fingerprint(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding: the ORM's masker had no key, so a SQLite N+1 lost its relationship and the report its fingerprint."""
    monkeypatch.setenv("SHARPIT_STATE_DIR", str(pytester.path / "state"))
    pytester.makepyfile(NPLUS_ONE)
    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )
    assert result.ret in (0, 1)
    findings = json.loads((pytester.path / "report.json").read_text())["findings"]
    assert [finding for finding in findings if "Owner.pets" in str(finding.get("message"))] != []


def test_sqlite_without_a_key_is_unknown_and_can_be_allowed(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = pytester.path / "state"
    state_dir.write_text("not a directory")
    monkeypatch.setenv("SHARPIT_STATE_DIR", str(state_dir))
    pytester.makepyfile(NPLUS_ONE)

    result = pytester.runpytest_subprocess("--sharpit", "--sharpit-no-advisors", "--sharpit-report=report.json", "-q")

    report = json.loads((pytester.path / "report.json").read_text())
    assert result.ret != 0
    assert any("source 'sqlite3' not attached" in reason for reason in report["unknownReasons"])

    allowed = pytester.runpytest(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=allowed.json", "-q"
    )
    assert allowed.ret == 0
    allowed_report = json.loads((pytester.path / "allowed.json").read_text())
    assert allowed_report["status"] == "unknown"


def test_the_env_key_appears_in_no_output(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch) -> None:
    key = "x" * 32
    state_dir = pytester.path / "state"
    monkeypatch.setenv("SHARPIT_STATE_DIR", str(state_dir))
    monkeypatch.setenv("SHARPIT_IDENTITY_KEY", key)
    pytester.makepyfile("def test_pass(): pass")
    result = pytester.runpytest_subprocess(
        "--sharpit", "--sharpit-no-advisors", "--sharpit-allow-unknown", "--sharpit-report=report.json", "-q"
    )
    assert result.ret == 0
    assert key not in result.stdout.str()
    assert key not in (pytester.path / "report.json").read_text()
    assert not (state_dir / "identity.key").exists()
