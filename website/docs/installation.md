# Installation

Install sharpit from PyPI with the FastAPI host extra:

```bash
pip install "sharpit[fastapi]"
# or
uv add "sharpit[fastapi]"
```

Python 3.12+. Runtime dependencies are only `starlette>=0.44` and `packaging>=23`. Optional extras:

| Extra | Adds | Why |
|---|---|---|
| `sharpit[fastapi]` | `fastapi>=0.115` | the supported host |
| `sharpit[settings]` | `pydantic-settings>=2.4` | the Config panel shows which source each value came from |
| `sharpit[test]` | sharpit's own test dependencies | running sharpit's test suite; contributors only |

## Which panel needs which library

sharpit never imports a database or telemetry library. It reads the ones your application has already imported (from
`sys.modules`), so a panel whose library your app does not use says why it is unavailable and costs nothing. Only
FastAPI and pydantic-settings have an extra; every other library is one your app installs for its own reasons.

| Panel | Library | Extra | Notes |
|---|---|---|---|
| all panels | FastAPI 0.115+ | `sharpit[fastapi]` | the supported host |
| `config` | pydantic-settings 2.4+ | `sharpit[settings]` | provenance only: without it Config still shows env, `.env` and `os.getenv` keys |
| `sql-trace` | SQLAlchemy 2.0+ | none: your app brings it | the raw `sqlite3` module is traced without SQLAlchemy |
| `sqlalchemy-statistics` | SQLAlchemy 2.0+ | none: your app brings it | reads the SQL Trace totals |
| `database-connection-pools` | SQLAlchemy 2.0+ | none: your app brings it | pool settings and live counters |
| `data` | SQLAlchemy 2.0+ | none: your app brings it | needs `install(app, models=Base)` |
| `transactions` | SQLAlchemy 2.0+ | none: your app brings it | SQLAlchemy connection events |
| `database-advisor` | SQLAlchemy 2.0+ | none: your app brings it | reads the schema through a read-only connection |
| `postgresql` | SQLAlchemy 2.0+ and a PostgreSQL driver | none: your app brings them | tested with psycopg 3 |
| `mysql` | SQLAlchemy 2.0+ and a MySQL or MariaDB driver | none: your app brings them | tested with PyMySQL; `asyncmy` and `mysqlclient` are untested |
| `traces` | OpenTelemetry SDK (`opentelemetry-sdk`) | none: your app brings it | needs the app's own SDK `TracerProvider`; sharpit installs none |
| none (running sharpit's own tests) | the test dependencies of the repository | `sharpit[test]` | contributors only; no panel needs it |

The `alembic` panel needs no library: it reads `alembic.ini` (or `[tool.alembic]`) and the revision files.
