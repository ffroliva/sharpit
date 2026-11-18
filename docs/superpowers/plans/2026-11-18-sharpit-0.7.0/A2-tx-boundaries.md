# A2: observed transaction boundaries

> **For agentic workers:** one task at a time; `/sharpit:check` before every commit; `scripts/dev/red_check.py`
> before every `test:` commit. Read the named BootUI files at `v2.4.0` in a BootUI clone; never from a summary.

**Goal:** a transaction row's `propagation` states what the SQLAlchemy events show: `NEW`, `REQUIRES_NEW`, `NESTED` or
`UNKNOWN`, never the declared `PARTICIPATING`. A begin that fails is a row of its own: `UNKNOWN`, with no SQL
statements and no connections.

**Predict verdict:** CAUTION 6/10 (a label that claims more than SQLAlchemy shows). `UNKNOWN` is the answer whenever
ownership is not verified.

**Production path changed:** `src/sharpit/engine/capture/transactions.py`: `TransactionRecorder.begin` (row
construction, formerly `"PARTICIPATING" if parent is not None else "NEW"`), `TransactionRecorder.report` (SQL
correlation), `_begin` and `tx_savepoint` (the class listeners `begin` and `savepoint`), and `tx_handle_error` (the
`handle_error` listener). Every route, MCP tool and CLI tool that reads transactions goes through `context_report`
and `TransactionRecorder.report`, so no reader changes.

**BootUI source (2.4.0):** `engine/transactions/TransactionBoundary.java` (`observed`),
`TransactionRecorder.java:61-66,271` (`begun`, `boundaryKnown`), `TransactionRecorderTests` (four cases).

## Observed boundary rules

`observed(known, nested, savepoint)` is BootUI's: `not known` is `UNKNOWN`, then `savepoint` is `NESTED`, then
`nested` is `REQUIRES_NEW`, else `NEW`. `nested` is "the recorder holds an enclosing row" (`parentId` set), as in BootUI.

| Scenario | Expected `propagation` | `parentId` |
|---|---|---|
| A root begin, nothing else live | `NEW` | null |
| `begin_nested()` / SAVEPOINT inside a recorded outer | `NESTED` | the outer row |
| A SAVEPOINT whose outer begin was not recorded | `NESTED` | null |
| A second connection begins while another live, non-AUTOCOMMIT transaction of the same task or thread is open on a different DBAPI connection | `REQUIRES_NEW` | the outer row; `nestedCount` counts it |
| The two SQLAlchemy connections share one DBAPI connection (`StaticPool`) | `UNKNOWN` | null |
| The outer connection is AUTOCOMMIT (not a transaction) | `NEW` | null |
| This connection is AUTOCOMMIT while another transaction is live | `UNKNOWN` | null |
| `asyncio.gather` siblings, each on its own connection | `NEW` each | null |
| Sequential transactions on two connections | `NEW` each | null |
| A child task (`asyncio.create_task`) or executor thread inherits the parent's open transaction | `UNKNOWN` | null |
| The begin fails (`do_begin` raises; the pysqlite `BEGIN` listener recipe fails) | `UNKNOWN`, `status` `UNKNOWN`, `errorMessage` masked, `sqlStatementCount` 0, `connectionCount` 0 | as at the begin |
| The commit or the rollback fails | not a failed begin: the row keeps its boundary | unchanged |
| The `SAVEPOINT` statement fails | the savepoint row is `UNKNOWN`, begun false; the frame is dropped; the outer row stays open | the outer row |
| A completion outcome (`COMMITTED`, `ROLLED_BACK`, `UNKNOWN`) | never changes `propagation` | unchanged |
| A connect failure (no begin event) | not recorded (`n-a`) | |
| The activity feed and the request profile "begin failed" wording | `n-a`: the feed is built from panel buffers and the profile has no transaction slot | |

## Decisions

- The ownership check follows `contextvars`: the open connections of a context are held weakly with the task (or, outside
  a task, the thread) that began them. A begin whose open transaction belongs to another task or thread is `UNKNOWN`.
- A begin on a connection that no enabled recorder routes to is not tracked, so a paused or unrouted outer never
  makes a later transaction `REQUIRES_NEW`.
- `TransactionBoundary.journalPropagation` and `independent` are not ported here: nothing reads them until the journal
  source (B2), which adds them with its tests.
- The 2.2.0 golden keeps `PARTICIPATING` as history; the 2.4.0 parity row reads the observed values.

## Tasks

- [ ] **Step 1:** `docs:` this file and the matrix fragment `docs/reference/matrix-updates/a2-tx-boundaries.tsv`.
- [ ] **Step 2:** `test:` `observed()` table; recorder cases ported from `TransactionRecorderTests` (parent and child,
      physical children, savepoints and failed begins, completion outcome, failed begin without SQL or connections).
- [ ] **Step 3:** `feat:` `TransactionBoundary`, `observed()`, `TransactionRecorder.begin(savepoint, known)`,
      `TransactionRecorder.fail_begin`, the report's SQL correlation skips a begin that did not happen.
- [ ] **Step 4:** `test:` SQLAlchemy shapes: savepoint, second connection, `StaticPool`, AUTOCOMMIT outer, `gather`
      siblings, sequential, child task, failed `do_begin`, the pysqlite `BEGIN` recipe, commit failure, failed
      `SAVEPOINT`, masked begin error.
- [ ] **Step 5:** `feat:` the observed context (`_OPEN`, `_autocommit`), the begin listener, `tx_handle_error`.
- [ ] **Step 6:** `test:` update `tests/fastapi/test_transactions_api.py` and the UI component fixture to the observed
      values; the overhead budget runs alone with `-n 0` and its `BUDGET_NS` is unchanged.
- [ ] **Step 7:** `docs:` CHANGELOG (Changed: the `propagation` value set), matrix rows, gates.
