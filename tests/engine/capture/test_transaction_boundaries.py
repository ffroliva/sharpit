"""Observed transaction boundaries: what SQLAlchemy's events show, never what an application declared."""

from __future__ import annotations

import asyncio
import gc
import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from multiprocessing.pool import ThreadPool
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


def test_an_error_on_a_shared_dbapi_connection_does_not_fail_another_connection_row(
    recorder: TransactionRecorder, sa: Any
) -> None:
    engine = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool, connect_args={"check_same_thread": False})
    with engine.connect() as first, engine.connect() as second:
        outer = first.begin()
        first.exec_driver_sql("create table tx_probe (value integer)")
        first.exec_driver_sql("insert into tx_probe values (1)")
        with pytest.raises(sa.exc.OperationalError):
            second.exec_driver_sql("select * from missing_tx_probe")
        outer.commit()
        assert first.exec_driver_sql("select value from tx_probe").scalar_one() == 1, (
            "the first connection's row commits"
        )
    rows = _by_id(recorder.report([]))
    assert rows[0]["status"] == "COMMITTED", "the error on the shared record cannot fail connection A"
    assert rows[0]["propagation"] == "NEW", "the first observed boundary keeps its original classification"
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


def test_engine_level_autocommit_outer_does_not_make_a_requires_new_boundary(
    recorder: TransactionRecorder, sa: Any
) -> None:
    engine = _engine(sa, isolation_level="AUTOCOMMIT")
    with engine.connect() as first, engine.connect() as second:
        outer = first.begin()
        inner = second.begin()
        inner.commit()
        outer.commit()
    outer_row, inner_row = _by_id(recorder.report([]))
    assert outer_row["propagation"] == "NEW", "the engine's AUTOCOMMIT setting is detected"
    assert inner_row["propagation"] == "NEW", "an AUTOCOMMIT outer is not a REQUIRES_NEW parent"
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


@pytest.mark.asyncio
async def test_default_asyncio_executor_jobs_do_not_share_boundary_ownership(
    recorder: TransactionRecorder, sa: Any
) -> None:
    engine = _engine(sa, connect_args={"check_same_thread": False})
    asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=1, thread_name_prefix="asyncio"))

    def open_outer() -> tuple[Any, Any]:
        connection = engine.connect()
        return connection, connection.begin()

    connection, transaction = await asyncio.get_running_loop().run_in_executor(None, open_outer)

    def inner() -> None:
        with engine.connect() as other:
            other.begin().commit()

    await asyncio.get_running_loop().run_in_executor(None, inner)
    await asyncio.get_running_loop().run_in_executor(None, transaction.commit)
    connection.close()
    outer_row, inner_row = _by_id(recorder.report([]))
    assert outer_row["propagation"] == "NEW", "the first asyncio worker job opens NEW"
    assert inner_row["propagation"] == "UNKNOWN", "a later asyncio worker job does not inherit ownership"
    engine.dispose()


def test_a_reused_executor_worker_does_not_claim_a_previous_jobs_parent(
    recorder: TransactionRecorder, sa: Any, tmp_path: Any
) -> None:
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'transactions.db'}", pool_size=2)
    with ThreadPoolExecutor(max_workers=1) as executor:
        outer = executor.submit(lambda: (engine.connect(), None)).result()[0]
        outer_tx = executor.submit(outer.begin).result()
        inner = executor.submit(engine.connect).result()
        executor.submit(lambda: inner.begin().commit()).result()
        executor.submit(outer_tx.commit).result()
        inner.close()
        outer.close()
    outer_row, inner_row = _by_id(recorder.report([]))
    assert outer_row["propagation"] == "NEW", "the first job owns its own boundary"
    assert inner_row["propagation"] == "UNKNOWN", "a reused executor worker does not claim a prior job's parent"
    assert inner_row["parentId"] is None, "an unverified owner names no parent"
    engine.dispose()


def test_a_single_executor_job_can_observe_its_own_physical_child(recorder: TransactionRecorder, sa: Any) -> None:
    engine = _engine(sa)

    def work() -> None:
        with engine.connect() as first, engine.connect() as second:
            outer = first.begin()
            inner = second.begin()
            inner.commit()
            outer.commit()

    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(work).result()
    outer_row, inner_row = _by_id(recorder.report([]))
    assert outer_row["propagation"] == "NEW", "the first physical begin is NEW"
    assert inner_row["propagation"] == "REQUIRES_NEW", "one job's physical child has the same owner"
    engine.dispose()


@pytest.mark.parametrize("pool_kind", ["executor", "multiprocessing"])
def test_reused_thread_pool_jobs_do_not_share_boundary_ownership(
    recorder: TransactionRecorder, sa: Any, tmp_path: Any, pool_kind: str
) -> None:
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'pool-ownership.db'}", pool_size=2)
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="db") if pool_kind == "executor" else ThreadPool(1)
    try:

        def run(call: Any) -> Any:
            return pool.submit(call).result() if pool_kind == "executor" else pool.apply(call)

        outer = run(engine.connect)
        outer_tx = run(outer.begin)
        inner = run(engine.connect)
        run(lambda: inner.begin().commit())
        run(outer_tx.commit)
        inner.close()
        outer.close()
    finally:
        pool.shutdown(wait=True) if pool_kind == "executor" else pool.close()
        if pool_kind == "multiprocessing":
            pool.join()
    outer_row, inner_row = _by_id(recorder.report([]))
    assert outer_row["propagation"] == "NEW", "the first worker job owns a NEW boundary"
    assert inner_row["propagation"] == "UNKNOWN", "worker reuse does not transfer ownership between jobs"
    engine.dispose()


def test_a_cleared_recorder_row_is_not_reused_as_a_parent(recorder: TransactionRecorder, sa: Any) -> None:
    engine = _engine(sa)
    with engine.connect() as first, engine.connect() as second:
        outer = first.begin()
        recorder.clear()
        inner = second.begin()
        inner.commit()
        outer.rollback()
    (row,) = _by_id(recorder.report([]))
    assert row["propagation"] == "NEW", "a cleared row cannot be named as a parent"
    assert row["parentId"] is None, "the report never references an absent parent id"
    engine.dispose()


def test_a_later_statement_error_does_not_resettle_a_committed_row(
    recorder: TransactionRecorder, sa: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sharpit.engine.capture.correlation import internal

    engine = _engine(sa)
    settled: list[int] = []
    settle = recorder.settle

    def track_settle(entry_id: int, error: BaseException | None = None) -> None:
        settled.append(entry_id)
        settle(entry_id, error)

    monkeypatch.setattr(recorder, "settle", track_settle)
    with engine.connect() as connection:
        connection.begin().commit()
        with internal():
            connection.begin()
        settled_before_statement = len(settled)
        with internal(), pytest.raises(sa.exc.OperationalError):
            connection.exec_driver_sql("select * from missing_tx_probe")
        assert len(settled) == settled_before_statement, "a statement error cannot settle a previous commit"
        connection.rollback()
    (row,) = recorder.report([])["entries"]
    assert row["status"] == "COMMITTED", "an internal statement error cannot rewrite an earlier commit"
    engine.dispose()


def test_commits_on_a_shared_record_keep_each_connections_pending_row(
    recorder: TransactionRecorder, sa: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool, connect_args={"check_same_thread": False})
    settled: list[int] = []
    settle = recorder.settle

    def track_settle(entry_id: int, error: BaseException | None = None) -> None:
        settled.append(entry_id)
        settle(entry_id, error)

    monkeypatch.setattr(recorder, "settle", track_settle)
    with engine.connect() as first, engine.connect() as second:
        first.begin().commit()
        second.begin().commit()
    rows = _by_id(recorder.report([]))
    assert len(rows) == 2, "both physical begins remain recorded"
    assert [row["status"] for row in rows] == ["COMMITTED", "COMMITTED"], "commit callbacks retain both pending rows"
    assert len(settled) == 2, "pool checkin settles both connections' commit rows"
    engine.dispose()


@pytest.mark.parametrize("other_state", ["pending_commit", "open_savepoint"])
def test_shared_record_state_on_another_connection_does_not_hide_failed_begin(
    recorder: TransactionRecorder, sa: Any, monkeypatch: pytest.MonkeyPatch, other_state: str
) -> None:
    engine = sa.create_engine("sqlite://", poolclass=sa.pool.StaticPool, connect_args={"check_same_thread": False})
    fail = {"on": False}
    original = engine.dialect.do_begin

    def do_begin(dbapi_connection: Any) -> None:
        if fail["on"]:
            raise sqlite3.OperationalError("refused")
        original(dbapi_connection)

    monkeypatch.setattr(engine.dialect, "do_begin", do_begin)
    with engine.connect() as first, engine.connect() as second:
        outer = first.begin()
        if other_state == "pending_commit":
            outer.commit()
        else:
            first.begin_nested()
        fail["on"] = True
        with pytest.raises((sa.exc.OperationalError, sqlite3.OperationalError)):
            second.begin()
        fail["on"] = False
        if other_state == "open_savepoint":
            outer.commit()
    rows = _by_id(recorder.report([]))
    failed = rows[-1]
    assert failed["status"] == "UNKNOWN", "another connection's state cannot mask this failed begin"
    assert failed["connectionCount"] == 0, "the failed begin owns no connection"
    assert rows[0]["status"] == "COMMITTED", "the other connection's row remains unaffected"
    engine.dispose()


def test_a_connection_that_begins_again_gets_a_fresh_open_transaction_identity(
    recorder: TransactionRecorder, sa: Any
) -> None:
    engine = _engine(sa)
    with engine.connect() as connection:
        connection.begin().commit()
        connection.begin().commit()
    rows = _by_id(recorder.report([]))
    assert [row["propagation"] for row in rows] == ["NEW", "NEW"], "a new SQLAlchemy transaction has a fresh identity"
    assert [row["parentId"] for row in rows] == [None, None], "a prior transaction object cannot be its parent"
    engine.dispose()


def test_an_open_entry_from_a_previous_transaction_object_is_not_a_parent() -> None:
    import threading
    import weakref

    from sharpit.engine.capture import transactions

    recorder = _recorder()
    entry_id = _begin(recorder)
    old_transaction, current_transaction = object(), object()

    class Connection:
        def in_transaction(self) -> bool:
            return True

        def get_transaction(self) -> object:
            return current_transaction

    connection = Connection()
    if hasattr(transactions.Owner, "_fields"):
        owner = transactions.Owner(threading.get_ident(), "MainThread", None, None, None)
    else:
        owner = (threading.get_ident(), None, None, False)
    opened = [weakref.ref(connection), owner, 1, {id(recorder): entry_id}, False]
    if "transaction_id" in transactions.OpenTransaction._fields:
        opened.extend([id(old_transaction), {id(recorder): weakref.ref(recorder)}])
    token = transactions._OPEN.set((transactions.OpenTransaction(*opened),))
    try:
        live, known, parents = transactions._other_open_transactions(owner, 2)
    finally:
        transactions._OPEN.reset(token)
        recorder.end(entry_id, "UNKNOWN")
    assert live == [], "a replaced root transaction is not live under the old entry"
    assert known, "a stale transaction identity is ignored rather than making the new boundary uncertain"
    assert parents == {}, "the new transaction cannot name a stale parent's row"


def test_a_garbage_collected_connection_does_not_leave_an_open_pooled_stack_item(
    recorder: TransactionRecorder, sa: Any
) -> None:
    engine = sa.create_engine("sqlite:///:memory:", poolclass=sa.pool.SingletonThreadPool)

    def leak() -> None:
        connection = engine.connect()
        connection.begin()

    leak()
    gc.collect()
    with engine.connect() as connection:
        connection.begin().commit()
        assert len(connection.info["sharpit_tx"]) == 0, "the next begin prunes stale rows from the pooled record"
    rows = _by_id(recorder.report([]))
    assert rows[0]["status"] == "UNKNOWN", "a dropped transaction closes as unknown"
    assert rows[1]["parentId"] is None, "a stale pooled row cannot become a parent"
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


def test_a_failing_commit_is_not_a_failed_begin(recorder: TransactionRecorder, sa: Any) -> None:
    base = sa.create_engine("sqlite://")
    engine = sa.create_engine("sqlite://", creator=lambda: _FailingDbapi(base.pool._creator(), ""))  # noqa: SLF001
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.connection.dbapi_connection.fails = "commit"
        with pytest.raises(sa.exc.OperationalError):
            transaction.commit()
        connection.connection.dbapi_connection.fails = ""
    (row,) = recorder.report([])["entries"]
    assert row["propagation"] == "NEW", "the boundary was observed when the transaction began"
    assert row["connectionCount"] == 1, "a transaction that began held its connection"
    assert row["status"] in {"UNKNOWN", "ROLLED_BACK"}, "the failed end is not reported as a commit"
    engine.dispose()
    base.dispose()


def test_a_failing_rollback_is_not_a_failed_begin(recorder: TransactionRecorder, sa: Any) -> None:
    base = sa.create_engine("sqlite://")
    engine = sa.create_engine("sqlite://", creator=lambda: _FailingDbapi(base.pool._creator(), ""))  # noqa: SLF001
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.connection.dbapi_connection.fails = "rollback"
        with pytest.raises(sa.exc.OperationalError):
            transaction.rollback()
        connection.connection.dbapi_connection.fails = ""
    (row,) = recorder.report([])["entries"]
    assert row["propagation"] == "NEW", "the boundary was observed when the transaction began"
    assert row["connectionCount"] == 1, "a transaction that began held its connection"
    assert row["status"] == "ROLLED_BACK", "the failed rollback does not turn begin into a failure"
    engine.dispose()
    base.dispose()


def test_a_failed_savepoint_at_depth_two_does_not_fail_the_outer_savepoint(
    recorder: TransactionRecorder, sa: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _engine(sa)
    refuse = {"on": False}
    do_savepoint = engine.dialect.do_savepoint

    def _refuse(connection: Any, name: str) -> None:
        if refuse["on"]:
            raise sqlite3.OperationalError("savepoint refused")
        do_savepoint(connection, name)

    monkeypatch.setattr(engine.dialect, "do_savepoint", _refuse)

    with engine.connect() as connection:
        outer = connection.begin()
        first_savepoint = connection.begin_nested()
        refuse["on"] = True
        with pytest.raises((sa.exc.OperationalError, sqlite3.OperationalError)):
            connection.begin_nested()
        refuse["on"] = False
        first_savepoint.commit()
        with pytest.raises(sa.exc.OperationalError):
            connection.exec_driver_sql("select * from missing_tx_probe")
        outer.commit()
    rows = _by_id(recorder.report([]))
    assert rows[0]["status"] == "COMMITTED", "a later statement error must not fail the outer row"
    assert rows[1]["status"] == "COMMITTED", "the released savepoint remains committed"
    assert rows[2]["status"] == "UNKNOWN", "the failed depth-two savepoint is detected"
    engine.dispose()


def test_a_failed_savepoint_drops_its_row_and_leaves_the_outer_open(
    recorder: TransactionRecorder, sa: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _engine(sa)
    refuse = {"on": True}
    do_savepoint = engine.dialect.do_savepoint

    def _refuse(connection: Any, name: str) -> None:
        if refuse["on"]:
            raise sqlite3.OperationalError("savepoint refused password=hunter2")
        do_savepoint(connection, name)

    monkeypatch.setattr(engine.dialect, "do_savepoint", _refuse)

    with engine.connect() as connection:
        outer = connection.begin()
        with pytest.raises((sa.exc.OperationalError, sqlite3.OperationalError)):
            connection.begin_nested()
        refuse["on"] = False
        retry = connection.begin_nested()
        retry_frames = list(connection.info["sharpit_tx_savepoints"])
        retry.commit()
        outer.commit()
    outer_row, failed_row, savepoint_row = _by_id(recorder.report([]))
    assert len(retry_frames) == 1, "the failed frame is dropped before the next savepoint is tracked"
    assert failed_row["propagation"] == "UNKNOWN", "a SAVEPOINT that failed is not a nested boundary anyone observed"
    assert failed_row["status"] == "UNKNOWN", "a failed SAVEPOINT neither committed nor rolled back"
    assert failed_row["connectionCount"] == 0, "a failed SAVEPOINT holds no connection"
    assert failed_row["parentId"] == outer_row["id"], "the failed SAVEPOINT names its outer transaction"
    assert "hunter2" not in failed_row["errorMessage"], "the SAVEPOINT error is masked"
    assert outer_row["status"] == "COMMITTED", "a failed SAVEPOINT does not close its outer transaction"
    assert savepoint_row["propagation"] == "NESTED", "the next SAVEPOINT is observed normally"
    assert savepoint_row["status"] == "COMMITTED", "the next SAVEPOINT closes with its own release"
    engine.dispose()


def test_a_user_savepoint_error_does_not_drop_the_pending_nested_frame(recorder: TransactionRecorder, sa: Any) -> None:
    engine = _engine(sa)

    @sa.event.listens_for(engine, "before_cursor_execute")
    def _refuse(_connection: Any, _cursor: Any, statement: str, *_rest: Any) -> None:
        if statement == "SAVEPOINT user_savepoint":
            raise sqlite3.OperationalError("user savepoint refused")

    with engine.connect() as connection:
        outer = connection.begin()
        nested = connection.begin_nested()
        with pytest.raises((sa.exc.OperationalError, sqlite3.OperationalError)):
            connection.exec_driver_sql("SAVEPOINT user_savepoint")
        assert len(connection.info["sharpit_tx_savepoints"]) == 1, "a raw SAVEPOINT error leaves the live frame"
        nested.rollback()
        outer.commit()
    rows = _by_id(recorder.report([]))
    assert rows[1]["status"] == "ROLLED_BACK", "the nested transaction ends through its rollback event"
    assert rows[0]["status"] == "COMMITTED", "the outer transaction remains live"
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
