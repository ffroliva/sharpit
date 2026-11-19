"""Observed transaction boundaries: what SQLAlchemy's events show, never what an application declared."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from typing import Any

import pytest

from sharpit.engine.capture.transaction_boundary import TransactionBoundary, observed
from sharpit.engine.capture.transactions import TransactionRecorder, attach
from sharpit.engine.masking import Masker
from sharpit.engine.sources import dispatch

# --- the recorder alone: BootUI's TransactionRecorderTests, the parent a caller names ---------------------------------


def _recorder(**options: object) -> TransactionRecorder:
    return TransactionRecorder(Masker("MASKED", True, None), application=lambda: None, **options)  # type: ignore[arg-type]


def _begin(recorder: TransactionRecorder, *, parent: int | None = None, **options: Any) -> int:
    return recorder.begin(
        1,
        parent=parent,
        method="orders:create",
        thread="MainThread",
        trace_id=None,
        connection_id=options.pop("connection_id", "db-1"),
        **options,
    )


def _by_id(report: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(report["entries"], key=lambda row: row["id"])


# derived: TransactionBoundary.observed(known, nested, savepoint)
@pytest.mark.parametrize(
    ("known", "nested", "savepoint", "wanted"),
    [
        (True, False, False, "NEW"),
        (True, True, False, "REQUIRES_NEW"),
        (True, False, True, "NESTED"),
        (True, True, True, "NESTED"),
        (False, False, False, "UNKNOWN"),
        (False, True, False, "UNKNOWN"),
        (False, False, True, "UNKNOWN"),
        (False, True, True, "UNKNOWN"),
    ],
)
def test_observed_boundary_table(known: bool, nested: bool, savepoint: bool, wanted: str) -> None:
    assert observed(known, nested, savepoint) == TransactionBoundary(wanted), (
        "an unknown boundary beats a savepoint, a savepoint beats a nested physical transaction"
    )


# ported: TransactionRecorderTests.tracksParentChildNestingOnTheSameThread
def test_a_physical_child_is_requires_new_and_counts_as_nested() -> None:
    recorder = _recorder()
    parent = _begin(recorder)
    child = _begin(recorder, parent=parent)
    recorder.end(child, "COMMITTED")
    recorder.end(parent, "COMMITTED")
    report = recorder.report([])
    rows = {row["id"]: row for row in report["entries"]}
    assert rows[child]["propagation"] == "REQUIRES_NEW", "a child with an enclosing row is physical and nested"
    assert rows[child]["parentId"] == parent, "the child names its enclosing row"
    assert rows[parent]["propagation"] == "NEW", "an unparented physical transaction is NEW"
    assert rows[parent]["parentId"] is None, "the outer row has no parent"
    assert report["stats"]["nestedCount"] == 1, "the child counts as nested"


# ported: TransactionRecorderTests.distinguishesPhysicalChildrenSavepointsAndFailedBeginsInBothReports
def test_physical_children_savepoints_and_failed_begins_are_told_apart() -> None:
    recorder = _recorder()
    parent = _begin(recorder)
    child = _begin(recorder, parent=parent)
    recorder.end(child, "COMMITTED")
    savepoint = _begin(recorder, parent=parent, savepoint=True)
    recorder.end(savepoint, "ROLLED_BACK")
    failed = _begin(recorder, parent=parent)
    recorder.fail_begin(failed, RuntimeError("begin failed"))
    recorder.end(parent, "ROLLED_BACK")
    rows = _by_id(recorder.report([]))
    assert [row["propagation"] for row in rows] == ["NEW", "REQUIRES_NEW", "NESTED", "UNKNOWN"], (
        "a physical child, a savepoint and a failed begin are three different boundaries"
    )
    assert [row["parentId"] for row in rows[1:]] == [parent] * 3, "every child names the outer row, a failed one too"
    assert rows[3]["status"] == "UNKNOWN", "a failed begin never reads as committed or rolled back"


# ported: TransactionRecorderTests.completionOutcomeDoesNotChangeTheObservedPhysicalBoundary
@pytest.mark.parametrize("status", ["COMMITTED", "ROLLED_BACK", "UNKNOWN"])
def test_the_completion_outcome_does_not_change_the_boundary(status: str) -> None:
    recorder = _recorder()
    outer = _begin(recorder)
    child = _begin(recorder, parent=outer)
    recorder.end(child, status, RuntimeError("completion"))
    recorder.end(outer, status)
    row = next(row for row in recorder.report([])["entries"] if row["id"] == child)
    assert row["propagation"] == "REQUIRES_NEW", "how a transaction ended says nothing about how it began"
    assert row["status"] == status, "the outcome is still reported"


# ported: TransactionRecorderTests.aFailedBeginDoesNotClaimSqlOrConnectionsFromItsCaller
def test_a_failed_begin_does_not_claim_sql_or_connections_from_its_caller() -> None:
    recorder = _recorder()
    ok = _begin(recorder, connection_id="caller-connection")
    recorder.end(ok, "COMMITTED")
    failed = _begin(recorder, connection_id="caller-connection")
    recorder.fail_begin(failed, RuntimeError("begin failed"))
    entries = recorder.report([])["entries"]
    sql_rows = [{"connectionId": "caller-connection", "timestamp": row["startTimestamp"]} for row in entries]
    rows = {row["id"]: row for row in recorder.report(sql_rows)["entries"]}
    assert rows[ok]["sqlStatementCount"] >= 1, "control: a begun transaction counts the statements on its connection"
    assert rows[ok]["connectionCount"] == 1, "control: a begun transaction holds one connection"
    assert rows[failed]["propagation"] == "UNKNOWN", "a begin that failed is not a boundary anyone observed"
    assert rows[failed]["sqlStatementCount"] == 0, "a failed begin claims none of its caller's statements"
    assert rows[failed]["connectionCount"] == 0, "a failed begin holds no connection"


def test_a_failed_begin_closes_its_row_and_masks_the_message() -> None:
    recorder = _recorder()
    failed = _begin(recorder)
    recorder.fail_begin(failed, RuntimeError("could not connect: password=hunter2"))
    row = recorder.report([])["entries"][0]
    assert row["status"] == "UNKNOWN", "the failed begin row is closed as unknown"
    assert row["endTimestamp"] is not None, "the failed begin row is closed"
    assert "hunter2" not in row["errorMessage"], "the failed begin message goes through the masker"


def test_fail_begin_ignores_a_row_that_is_not_open() -> None:
    recorder = _recorder()
    done = _begin(recorder)
    recorder.end(done, "COMMITTED")
    recorder.fail_begin(done, RuntimeError("late"))
    recorder.fail_begin(-1, RuntimeError("paused"))
    row = recorder.report([])["entries"][0]
    assert row["status"] == "COMMITTED", "a completed transaction is not rewritten by a later failure"
    assert row["propagation"] == "NEW", "a completed transaction keeps its boundary"


# --- SQLAlchemy's events -------------------------------------------------------------------------------------------


class _Context:
    """A fake sharpit context that, unlike SimpleNamespace, can be weakly referenced."""

    def __init__(self, recorder: TransactionRecorder) -> None:
        from types import SimpleNamespace

        self.context_id = "boundary-context"
        self.capture = SimpleNamespace(transactions=recorder, wiring=SimpleNamespace(hook_failed=lambda *_: None))
        self.settings = SimpleNamespace(
            transactions_enabled=True,
            panels={"transactions": SimpleNamespace(enabled=True)},
            sql_trace_capture_call_site=False,
        )


@pytest.fixture
def sa() -> Any:
    return pytest.importorskip("sqlalchemy")


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch, sa: Any) -> Iterator[TransactionRecorder]:
    recording = _recorder()
    targets = [_Context(recording)]
    monkeypatch.setattr(dispatch, "_targets", lambda _engine: targets)
    remove = attach()
    assert remove is not None, "the connection event slot should attach when SQLAlchemy is loaded"
    try:
        yield recording
    finally:
        remove()


def _engine(sa: Any, **options: Any) -> Any:
    """Every connection is its own DBAPI connection (and its own in-memory database)."""
    return sa.create_engine("sqlite://", poolclass=sa.pool.NullPool, **options)


def test_a_savepoint_is_nested_under_its_outer_transaction(recorder: TransactionRecorder, sa: Any) -> None:
    engine = _engine(sa)
    with engine.connect() as connection:
        outer = connection.begin()
        connection.begin_nested().commit()
        outer.commit()
    outer_row, savepoint_row = _by_id(recorder.report([]))
    assert outer_row["propagation"] == "NEW", "a transaction with nothing else open is NEW"
    assert savepoint_row["propagation"] == "NESTED", "a SAVEPOINT is a nested boundary"
    assert savepoint_row["parentId"] == outer_row["id"], "the savepoint names its outer transaction"
    engine.dispose()


def test_a_savepoint_whose_outer_begin_was_not_recorded_is_nested_without_a_parent(
    recorder: TransactionRecorder, sa: Any
) -> None:
    engine = _engine(sa)
    with engine.connect() as connection:
        recorder.set_recording(False)
        outer = connection.begin()
        recorder.set_recording(True)
        connection.begin_nested().commit()
        outer.commit()
    (savepoint_row,) = recorder.report([])["entries"]
    assert savepoint_row["propagation"] == "NESTED", "a SAVEPOINT is nested even when its outer was not recorded"
    assert savepoint_row["parentId"] is None, "an unrecorded outer cannot be named"
    engine.dispose()


def test_a_second_connection_begun_inside_an_open_transaction_is_requires_new(
    recorder: TransactionRecorder, sa: Any
) -> None:
    engine = _engine(sa)
    with engine.connect() as first, engine.connect() as second:
        outer = first.begin()
        inner = second.begin()
        inner.commit()
        outer.commit()
    report = recorder.report([])
    outer_row, inner_row = _by_id(report)
    assert outer_row["propagation"] == "NEW", "the outer transaction is NEW"
    assert inner_row["propagation"] == "REQUIRES_NEW", "a second physical transaction beside a live one"
    assert inner_row["parentId"] == outer_row["id"], "the second transaction names the live one"
    assert report["stats"]["nestedCount"] == 1, "the second transaction counts as nested"
    engine.dispose()


def test_connections_sharing_one_dbapi_connection_are_unknown(recorder: TransactionRecorder, sa: Any) -> None:
    engine = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool, connect_args={"check_same_thread": False})
    with engine.connect() as first, engine.connect() as second:
        outer = first.begin()
        inner = second.begin()
        inner.commit()
        outer.commit()
    outer_row, inner_row = _by_id(recorder.report([]))
    assert outer_row["propagation"] == "NEW", "the first transaction on a shared connection is NEW"
    assert inner_row["propagation"] == "UNKNOWN", "one DBAPI connection cannot hold two physical transactions"
    assert inner_row["parentId"] is None, "an unknown boundary names no parent"
    engine.dispose()


def test_an_autocommit_outer_connection_is_not_an_open_transaction(recorder: TransactionRecorder, sa: Any) -> None:
    engine = _engine(sa)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as first, engine.connect() as second:
        outer = first.begin()
        inner = second.begin()
        inner.commit()
        outer.commit()
    _outer_row, inner_row = _by_id(recorder.report([]))
    assert inner_row["propagation"] == "NEW", "an AUTOCOMMIT connection holds no transaction to nest in"
    assert inner_row["parentId"] is None, "nothing encloses the second transaction"
    engine.dispose()


def test_an_autocommit_connection_beside_an_open_transaction_is_unknown(recorder: TransactionRecorder, sa: Any) -> None:
    engine = _engine(sa)
    with engine.connect() as first, engine.connect().execution_options(isolation_level="AUTOCOMMIT") as second:
        outer = first.begin()
        inner = second.begin()
        inner.commit()
        outer.commit()
    _outer_row, inner_row = _by_id(recorder.report([]))
    assert inner_row["propagation"] == "UNKNOWN", "an AUTOCOMMIT begin is not a second physical transaction"
    engine.dispose()


def test_sequential_transactions_on_two_connections_are_each_new(recorder: TransactionRecorder, sa: Any) -> None:
    engine = _engine(sa)
    with engine.connect() as first:
        first.begin().commit()
        with engine.connect() as second:
            second.begin().commit()
    rows = _by_id(recorder.report([]))
    assert [row["propagation"] for row in rows] == ["NEW", "NEW"], "a finished transaction is not an enclosing one"
    assert [row["parentId"] for row in rows] == [None, None], "nothing encloses a later transaction"
    engine.dispose()


@pytest.mark.asyncio
async def test_gathered_siblings_are_not_nested_in_each_other(recorder: TransactionRecorder, sa: Any) -> None:
    engine = _engine(sa)
    both_open = asyncio.Barrier(2)

    async def work() -> None:
        with engine.connect() as connection:
            transaction = connection.begin()
            await both_open.wait()
            transaction.commit()

    await asyncio.gather(work(), work())
    rows = _by_id(recorder.report([]))
    assert [row["propagation"] for row in rows] == ["NEW", "NEW"], "sibling tasks do not enclose one another"
    assert [row["parentId"] for row in rows] == [None, None], "siblings name no parent"
    engine.dispose()


@pytest.mark.asyncio
async def test_a_child_task_inheriting_an_open_transaction_is_unknown(recorder: TransactionRecorder, sa: Any) -> None:
    engine = _engine(sa)

    async def child() -> None:
        with engine.connect() as connection:
            connection.begin().commit()

    with engine.connect() as outer:
        transaction = outer.begin()
        await asyncio.create_task(child())
        transaction.commit()
    _outer_row, child_row = _by_id(recorder.report([]))
    assert child_row["propagation"] == "UNKNOWN", "a child task inherits the context, not the ownership"
    assert child_row["parentId"] is None, "an unknown boundary names no parent"
    engine.dispose()


@pytest.mark.asyncio
async def test_an_executor_thread_inheriting_an_open_transaction_is_unknown(
    recorder: TransactionRecorder, sa: Any
) -> None:
    engine = _engine(sa)

    def work() -> None:
        with engine.connect() as connection:
            connection.begin().commit()

    with engine.connect() as outer:
        transaction = outer.begin()
        await asyncio.to_thread(work)
        transaction.commit()
    _outer_row, worker_row = _by_id(recorder.report([]))
    assert worker_row["propagation"] == "UNKNOWN", "a worker thread copies the context, not the ownership"
    engine.dispose()


def _failing_begin(sa: Any, engine: Any, message: str, monkeypatch: pytest.MonkeyPatch, fail: dict[str, bool]) -> None:
    def do_begin(_dbapi_connection: Any) -> None:
        if fail["on"]:
            raise sqlite3.OperationalError(message)

    monkeypatch.setattr(engine.dialect, "do_begin", do_begin)


def test_a_failed_do_begin_is_unknown_with_no_sql_and_no_connection(
    recorder: TransactionRecorder, sa: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _engine(sa)
    fail = {"on": True}
    _failing_begin(sa, engine, "could not start password=hunter2", monkeypatch, fail)
    with engine.connect() as connection:
        with pytest.raises(sa.exc.OperationalError):
            connection.begin()
        fail["on"] = False
        failed_connection_id = hex(id(connection.connection.dbapi_connection))
        connection.begin().commit()
    failed_row, next_row = _by_id(recorder.report([]))
    sql = [{"connectionId": failed_connection_id, "timestamp": failed_row["startTimestamp"]}]
    failed_row = _by_id(recorder.report(sql))[0]
    assert failed_row["propagation"] == "UNKNOWN", "a begin that raised is not a boundary anyone observed"
    assert failed_row["status"] == "UNKNOWN", "a begin that raised neither committed nor rolled back"
    assert failed_row["endTimestamp"] is not None, "the failed begin row is closed"
    assert failed_row["sqlStatementCount"] == 0, "a failed begin claims no statements"
    assert failed_row["connectionCount"] == 0, "a failed begin holds no connection"
    assert "hunter2" not in failed_row["errorMessage"], "the begin error is masked"
    assert next_row["propagation"] == "NEW", "the next transaction on the connection starts clean"
    assert next_row["parentId"] is None, "the failed begin is nobody's parent"
    engine.dispose()


def test_a_failed_begin_beside_an_open_transaction_keeps_the_outer_as_its_parent(
    recorder: TransactionRecorder, sa: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _engine(sa)
    fail = {"on": False}
    _failing_begin(sa, engine, "refused", monkeypatch, fail)
    with engine.connect() as first, engine.connect() as second:
        outer = first.begin()
        fail["on"] = True
        with pytest.raises(sa.exc.OperationalError):
            second.begin()
        fail["on"] = False
        outer.commit()
    outer_row, failed_row = _by_id(recorder.report([]))
    assert failed_row["propagation"] == "UNKNOWN", "a failed begin is UNKNOWN beside a live transaction too"
    assert failed_row["parentId"] == outer_row["id"], "the failed begin still names the transaction it was begun in"
    assert outer_row["status"] == "COMMITTED", "a failed begin does not close the outer transaction"
    engine.dispose()


def test_a_failed_begin_in_the_pysqlite_begin_listener_recipe_is_unknown(
    recorder: TransactionRecorder, sa: Any
) -> None:
    """The pysqlite workaround issues BEGIN from a ``begin`` listener; its failure carries a statement."""
    engine = _engine(sa)
    fail = {"on": False}

    @sa.event.listens_for(engine, "connect")
    def _connect(dbapi_connection: Any, _record: Any) -> None:
        dbapi_connection.isolation_level = None

    @sa.event.listens_for(engine, "begin")
    def _begin_listener(connection: Any) -> None:
        connection.exec_driver_sql("BEGIN BOGUS" if fail["on"] else "BEGIN")

    with engine.connect() as connection:
        connection.begin().commit()
        fail["on"] = True
        with pytest.raises(sa.exc.OperationalError):
            connection.begin()
    ok_row, failed_row = _by_id(recorder.report([]))
    assert ok_row["propagation"] == "NEW", "control: the recipe's begin is an ordinary one"
    assert ok_row["status"] == "COMMITTED", "control: the recipe's transaction commits"
    assert failed_row["propagation"] == "UNKNOWN", "a BEGIN that failed is not a boundary anyone observed"
    assert failed_row["status"] == "UNKNOWN", "a failed BEGIN neither committed nor rolled back"
    assert failed_row["connectionCount"] == 0, "a failed BEGIN holds no connection"
    engine.dispose()


class _FailingDbapi:
    """A DBAPI connection that fails one named method, the way a dropped server would."""

    def __init__(self, connection: Any, fails: str) -> None:
        self.connection = connection
        self.fails = fails

    def __getattr__(self, name: str) -> Any:
        return getattr(self.connection, name)

    def commit(self) -> None:
        if self.fails == "commit":
            raise sqlite3.OperationalError("commit refused")
        self.connection.commit()

    def rollback(self) -> None:
        if self.fails == "rollback":
            raise sqlite3.OperationalError("rollback refused")
        self.connection.rollback()


@pytest.mark.parametrize("fails", ["commit", "rollback"])
def test_a_failing_commit_or_rollback_is_not_a_failed_begin(recorder: TransactionRecorder, sa: Any, fails: str) -> None:
    base = sa.create_engine("sqlite://")
    engine = sa.create_engine("sqlite://", creator=lambda: _FailingDbapi(base.pool._creator(), ""))  # noqa: SLF001
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.connection.dbapi_connection.fails = fails
        with pytest.raises(sa.exc.OperationalError):
            getattr(transaction, fails)()
        connection.connection.dbapi_connection.fails = ""
    (row,) = recorder.report([])["entries"]
    assert row["propagation"] == "NEW", "the boundary was observed when the transaction began"
    assert row["connectionCount"] == 1, "a transaction that began held its connection"
    assert row["status"] in {"UNKNOWN", "ROLLED_BACK"}, "the failed end is not reported as a commit"
    engine.dispose()
    base.dispose()


def test_a_failed_savepoint_drops_its_row_and_leaves_the_outer_open(recorder: TransactionRecorder, sa: Any) -> None:
    engine = _engine(sa)
    refuse = {"on": True}

    @sa.event.listens_for(engine, "before_cursor_execute")
    def _refuse(_connection: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        if refuse["on"] and statement.startswith("SAVEPOINT"):
            raise sqlite3.OperationalError("savepoint refused password=hunter2")

    with engine.connect() as connection:
        outer = connection.begin()
        with pytest.raises(sa.exc.OperationalError):
            connection.begin_nested()
        frames_after_failure = list(connection.info["sharpit_tx_savepoints"])
        refuse["on"] = False
        connection.begin_nested().commit()
        outer.commit()
    outer_row, failed_row, savepoint_row = _by_id(recorder.report([]))
    assert frames_after_failure == [], "a savepoint that failed to begin leaves no frame behind"
    assert failed_row["propagation"] == "UNKNOWN", "a SAVEPOINT that failed is not a nested boundary anyone observed"
    assert failed_row["status"] == "UNKNOWN", "a failed SAVEPOINT neither committed nor rolled back"
    assert failed_row["connectionCount"] == 0, "a failed SAVEPOINT holds no connection"
    assert failed_row["parentId"] == outer_row["id"], "the failed SAVEPOINT names its outer transaction"
    assert "hunter2" not in failed_row["errorMessage"], "the SAVEPOINT error is masked"
    assert outer_row["status"] == "COMMITTED", "a failed SAVEPOINT does not close its outer transaction"
    assert savepoint_row["propagation"] == "NESTED", "the next SAVEPOINT is observed normally"
    assert savepoint_row["status"] == "COMMITTED", "the next SAVEPOINT closes with its own release"
    engine.dispose()


def test_a_user_statement_error_is_not_a_failed_begin(recorder: TransactionRecorder, sa: Any) -> None:
    engine = _engine(sa)
    with engine.connect() as connection:
        transaction = connection.begin()
        with pytest.raises(sa.exc.OperationalError):
            connection.exec_driver_sql("select * from missing_table")
        transaction.rollback()
    (row,) = recorder.report([])["entries"]
    assert row["propagation"] == "NEW", "a failing statement inside a transaction leaves its boundary alone"
    assert row["status"] == "ROLLED_BACK", "the transaction still ends with its own rollback"
    assert row["connectionCount"] == 1, "the transaction held its connection"
    engine.dispose()
