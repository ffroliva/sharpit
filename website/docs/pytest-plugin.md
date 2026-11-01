# Pytest plugin

The sharpit pytest plugin turns runtime capture into findings you can gate CI on.
Running `pytest --sharpit` requires no changes to your application code. It tags every SQL statement
and observable exception with the running test, checks query budgets and N+1 patterns, runs offline advisors,
and generates JSON and JUnit reports.

## What `pytest --sharpit` does

When invoked with `--sharpit`, the plugin:

- Attaches capture hooks for SQLAlchemy and raw `sqlite3` before any tests run.
- Correlates queries and observable exceptions to the active test using context variables.
- Evaluates per-test query budgets, N+1 query patterns, and swallowed exceptions during the `call` phase.
- Runs offline static advisors (such as the REST API advisor) across all discovered ASGI applications.
- Writes a consolidated `sharpit-report/1` JSON report and optional JUnit XML.
- Returns exit code 1 if any gate fails, or if capture was incomplete (`unknown` status).

Without `--sharpit`, installing sharpit does not alter `pytest` execution. Importing the plugin registers options
and markers but performs no patching, sets no context variables, and opens no files.

## Options

Configure the plugin via command-line arguments or `pytest.ini` / `pyproject.toml`.
Command-line options take precedence over ini settings. Shared settings (such as masking and profiles)
continue to use `SHARPIT_*` environment variables.

| CLI option | ini key | Default | Description |
|---|---|---|---|
| `--sharpit` | `sharpit = true` | off | Turn the plugin on for this session |
| `--sharpit-report=PATH` | `sharpit_report` | `sharpit-report.json` | Path to write the JSON report (controller only) |
| `--sharpit-junit=PATH` | `sharpit_junit` | none | Path to write the JUnit XML report; omitted when unset |
| `--sharpit-max-queries=N` | `sharpit_max_queries` | none | Default per-test query budget for the call phase |
| `--sharpit-fail-on=SEV` | `sharpit_fail_on` | `HIGH` | Minimum advisor finding severity that fails the session |
| `--sharpit-allow-unknown` | `sharpit_allow_unknown = true` | off | Allow `unknown` run status without failing the build |
| `--sharpit-app=MOD:ATTR` | `sharpit_app` | none | Import path to ASGI app or factory for offline advisors |
| `--sharpit-no-advisors` | `sharpit_advisors = false` | advisors on | Run count gates only and skip advisor scans |
| `--sharpit-max-unattributed=PCT` | `sharpit_max_unattributed` | `10` | Maximum percentage of non-filtered statements allowed unattributed before run is `unknown` |

## Count gates and the marker

During the test `call` phase, the plugin evaluates three count gates defined by the `test-runtime` advisor:

| Rule ID | Fails when | Severity |
|---|---|---|
| `sharpit.max-queries` | Total executed queries exceed budget (via marker or `--sharpit-max-queries`) | `HIGH` |
| `sharpit.n-plus-one` | A single normalized `SELECT` group executes at or above threshold (default 5) | `HIGH` |
| `sharpit.exception` | Swallowed exceptions exceed `max_exceptions` (default 0) | `HIGH` |

A query is counted as one `execute`, one `executemany` batch, or one `executescript`.
N+1 detection groups queries by normalized fingerprint (folding literals, collapsing `IN` lists, and ignoring case).

### The `@pytest.mark.sharpit` marker

Use `@pytest.mark.sharpit` to set custom query limits or relax checks on specific tests:

```python
import pytest


@pytest.mark.sharpit(max_queries=5)
def test_list_items():
    pass


@pytest.mark.sharpit(allow_n_plus_one=True, max_exceptions=1)
def test_bulk_legacy_sync():
    pass
```

The marker accepts only three keyword arguments:

- `max_queries: int`: maximum queries allowed in the `call` phase.
- `allow_n_plus_one: bool`: allow N+1 query patterns without triggering a failure.
- `max_exceptions: int`: maximum allowed swallowed exceptions (default 0).

Any other argument raises `pytest.UsageError` during test collection.
The closest marker wins (function level over class level over module level).
Without `--sharpit`, the marker has no effect.

## Attribution and phases

### Attribution

Statements and exceptions are tracked in the thread and coroutine context using context variables.
A fact counts against a test only when its tagged `nodeid` and attempt number match the active test window.

Any fact that cannot be attributed to the active test goes to the **unattributed** bucket:

- Statements from uninstrumented background threads that do not propagate context.
- Stale tags from persistent workers started by earlier fixtures.
- Exceptions logged inside object finalizers (`__del__`, `_finalize_fairy`, weakref callbacks).

Unattributed statements are recorded in the report but are never gated against individual tests.
However, if unattributed queries exceed `--sharpit-max-unattributed` percent (default 10%) of non-filtered queries,
the session outcome becomes `unknown`.

### Test phases

Every statement and exception records the lifecycle phase: `setup`, `call`, or `teardown`.
Count gates apply exclusively to the `call` phase. Queries executed during fixture setup or teardown
are recorded in the report for visibility but do not fail test budgets.

### Built-in SQL filters

Database setup, migration verification, and transaction management frequently execute routine queries.
The test-session sink automatically filters these from gate evaluation:

- `PRAGMA ...`
- Reads from `sqlite_master`, `sqlite_schema`, or `sqlite_temp_master`
- Reads and writes to migration tables: `alembic_version`, `schema_migrations`, `flyway_schema_history`, `django_migrations`, and `knex_migrations`
- Transaction statements: `BEGIN`, `COMMIT`, `ROLLBACK`, `SAVEPOINT`, `RELEASE`

Filtered statements are counted in `filtered.count` but never count against query budgets or N+1 gates.

## Session status and outcomes

The session produces one of three overall statuses in the report:

1. `fail`: Any test failed a sharpit count gate, or an advisor run produced `FAILED`.
2. `unknown`: Capture could not observe enough to verify compliance. Occurs if:
   - No SQL source was attached at session end.
   - SQL queries were executed (`totals.queries > 0`), but none was attributed to any test (reason: `"no SQL statement was attributed to a test"`).
   - Pre-existing SQLite connections or early `from sqlite3 import connect` bindings were detected with zero attributed statements.
   - Unattributed statements exceeded `--sharpit-max-unattributed` percent (default 10%).
   - An untraced DB-API driver (`aiosqlite`, `asyncpg`, `psycopg`, `psycopg2`, `pymysql`, `MySQLdb`, `oracledb`, `pyodbc`) was imported without being backed by a detected SQLAlchemy engine.
   - An exception source failed to attach, or any worker reported `attached: false`.
   - An advisor ended with `UNKNOWN` (such as `rest-api` without an app: `"no application: pass --sharpit-app or call sharpit.install in the tests"`).
   - An xdist worker crashed or failed to return facts.
3. `pass`: All gates passed and advisors completed with full coverage. A test suite with zero database queries passes with a warning (`"no SQL statement was executed"`), provided no uninstrumented drivers were detected.

### Exit codes

- A `fail` status raises the pytest exit code to 1 if pytest would have returned 0.
- An `unknown` status raises the exit code to 1 unless `--sharpit-allow-unknown` is passed.
- Existing pytest failure exit codes are preserved and never lowered.

## Parallel runs with pytest-xdist

`pytest --sharpit` supports parallel execution with `pytest-xdist`:

- Each worker process attaches capture hooks and evaluates its own tests.
- Offline advisors run inside worker processes on application snapshots; the controller never imports application code.
- Workers send raw execution facts to the controller via `config.workeroutput`.
- The controller merges facts, evaluates session-level conditions (such as overall unattributed percentage and untraced drivers), and writes the final reports.
- When using rerun plugins, only the final attempt's gates determine test outcome.

## Safety model

The pytest plugin enforces strict safety rules:

- **Fails closed on disabled profiles**: If an active profile is in `SHARPIT_DISABLED_PROFILES` (such as `APP_ENV=production`), running `pytest --sharpit` fails immediately with `pytest.UsageError`. Setting `SHARPIT_ENABLED=OFF` together with `--sharpit` also raises `pytest.UsageError`.
- **No HTTP surface**: The plugin runs in-process only. It opens no listening ports, mounts no HTTP endpoints, and starts no server threads.
- **No parameters in reports**: Reports never contain SQL bind parameter values, regardless of `SHARPIT_SQL_TRACE_CAPTURE_PARAMETERS`.
- **Masked values**: The report masker always applies the default `MASKED` policy. If `SHARPIT_EXPOSE_VALUES=FULL` or `SHARPIT_MASK_SECRETS=false` is set, the report ignores it and adds a warning.

## Known limitations

- **aiosqlite worker thread**: `aiosqlite` runs queries on an internal worker thread that does not inherit Python context variables. Statements appear in the `unattributed` bucket and count toward the `--sharpit-max-unattributed` limit.
- **Connections opened before attach**: SQLite connections established before the plugin hook runs (or early `from sqlite3 import connect` imports) bypass tracing.
- **Direct `sqlite3.dbapi2.connect` calls**: Code calling `sqlite3.dbapi2.connect` directly is untraced.
- **Observable exceptions only**: The exception gate tracks swallowed exceptions logged at `ERROR` or above with `exc_info`, or handled by registered framework exception handlers. Silent `try...except` blocks that neither log nor re-raise leave no trace and cannot be detected.

## CI example

Here is a GitHub Actions job that runs `pytest --sharpit`, generates JUnit and JSON reports, and uploads them as build artifacts:

```yaml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install -e ".[test]"

      - name: Run tests with sharpit gates
        run: |
          pytest --sharpit --sharpit-junit=sharpit-junit.xml

      - name: Upload test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: sharpit-reports
          path: |
            sharpit-report.json
            sharpit-junit.xml
```
