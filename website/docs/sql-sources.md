# SQL sources

sharpit captures SQL queries executed by your application for live console analysis and automated test gating.
It supports both SQLAlchemy and Python's built-in `sqlite3` module.

## Supported drivers and architecture

In Python, there is no unified database driver proxy layer comparable to Java's JDBC `DataSource`.
sharpit uses **one SQL source per driver**, feeding a common dispatcher:

- **SQLAlchemy source**: Uses SQLAlchemy class-level listeners (`before_cursor_execute`, `after_cursor_execute`, `handle_error`) attached to `Engine`.
- **`sqlite3` source**: Replaces `sqlite3.connect` with a wrapper returning a `TracedConnection` and `TracedCursor`.

Both sources emit standardized statement events to `engine/sources/dispatch.py`, which routes them to console buffers and test session sinks.

### Preventing double-counting with SQLAlchemy on SQLite

SQLAlchemy connects to SQLite via Python's `sqlite3.dbapi2.connect`.
sharpit deliberately patches `sqlite3.connect` and never patches `sqlite3.dbapi2.connect`.
As a result, SQLAlchemy applications using SQLite have their queries recorded exclusively by the SQLAlchemy source,
preventing duplicate statement entries.

## Configuration: `SHARPIT_SQL_TRACE_SQLITE3_ENABLED`

Tracing raw `sqlite3` in the web console is controlled by:

- Environment variable: `SHARPIT_SQL_TRACE_SQLITE3_ENABLED` (default `true`)
- Keyword argument: `sharpit.install(app, sql_trace_sqlite3_enabled=True)`

Setting this to `false` keeps the raw `sqlite3` source detached during normal console operation.
In contrast, `pytest --sharpit` always attaches the `sqlite3` source during test runs regardless of this setting.

## The dev-wrapper pattern

For applications that open database connections during module import (such as CLI tools or background workers using raw `sqlite3`),
calling `sharpit.install(app)` after importing the application comes too late to trace early connections.

To trace early connections without modifying shipped application code, use the **dev-wrapper pattern**:

1. Create a wrapper module outside your package (for example `dev/sharpit_app.py`).
2. Call `sharpit.attach_sql_sources()` before importing the application module.
3. Import the application and call `sharpit.install(app)`.
4. Keep the wrapper module out of the shipped wheel, and declare `sharpit` only in a development dependency extra.

### Example dev wrapper

```python
import sharpit

# 1. Attach SQL tracing before importing the application:
sharpit.attach_sql_sources()

# 2. Import your application:
from myapp.main import app

# 3. Install sharpit dev console:
sharpit.install(app)
```

Run the application pointing to the wrapper:

```bash
uvicorn dev.sharpit_app:app --reload
```

Or run pytest targeting the wrapper:

```bash
pytest --sharpit --sharpit-app=dev.sharpit_app:app
```

`sharpit.attach_sql_sources()` checks `activation.decide()`. If a production profile is active,
it remains disabled and leaves `sqlite3.connect` untouched.

## `detach_sql_sources()`

To cleanly detach tracing programmatically:

```python
import sharpit

sharpit.detach_sql_sources()
```

`detach_sql_sources()` is idempotent. It verifies object identity before restoring `sqlite3.connect`,
ensuring it only unpatches if the function is still sharpit's wrapper. If another library has wrapped
`connect` in the meantime, sharpit logs a warning and leaves the active patch undisturbed.

## Limitations

- **Pre-existing connections**: Any `sqlite3.Connection` opened before `attach_sql_sources()` or `sharpit.install()` cannot be retroactively wrapped and will not be traced.
- **Early `connect` imports**: Modules that execute `from sqlite3 import connect` before attachment bind directly to the stdlib C function and bypass the wrapper.
- **Direct `sqlite3.dbapi2.connect` calls**: Code calling `sqlite3.dbapi2.connect` directly is untraced.
- **Custom factories**: Connection factories passed to `connect(factory=...)` that do not subclass `sqlite3.Connection` are passed through untraced.
- **Parameter masking**: Bind parameters are not captured by default. When enabled in the console (`SHARPIT_SQL_TRACE_CAPTURE_PARAMETERS=true`), positional parameters are masked by shape and vendor token prefixes (e.g. `sk_live_`, `ghp_`). Test reports never contain parameter values.
