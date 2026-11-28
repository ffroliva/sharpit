# Quickstart

Install sharpit and the FastAPI development server (`fastapi[standard]` provides `fastapi dev` and uvicorn):

```bash
pip install "sharpit[fastapi]" "fastapi[standard]"
```

Save this as `app.py`:

```python
from fastapi import FastAPI

import sharpit

app = FastAPI()


@app.get("/hello")
def hello() -> dict[str, str]:
    return {"message": "hello"}


# Register your application's middleware first:
# app.add_middleware(...)

# Install sharpit after your app's middleware:
sharpit.install(app)  # mounts /sharpit and /sharpit/api
```

Call `sharpit.install(app)` after adding your own middleware. Starlette builds middleware from the outside in, so
calling `install()` last ensures sharpit's capture middleware sits outside your application middleware. This lets sharpit
measure total request durations and record unhandled errors correctly.

Run it **with a dev signal** and open <http://127.0.0.1:8000/sharpit/>:

```bash
fastapi dev app.py          # or: uvicorn app:app --reload
```

Without a dev signal every path under `/sharpit` answers 404. A plain `uvicorn app:app`, or `uvicorn.run(...,
reload=True)` called from a script, is not detected: set `APP_ENV=dev` or `SHARPIT_ENABLED=ON`
([Activation](activation.md)).

Keyword arguments for `sharpit.install()`:

- `engines`: optional sequence of SQLAlchemy `Engine` or `AsyncEngine` instances to monitor in connection pools and
  health checks (e.g. `engines=[engine]`). If omitted, engines are discovered automatically on first connection.
- `health_checks`: optional mapping of check names to zero-argument callables (e.g. `health_checks={"cache": ping_cache}`).
- `alembic_config`: optional path to `alembic.ini` (default `"alembic.ini"`).
- `settings`: optional pydantic-settings instance or sequence of instances to show configuration provenance.
- `models`: optional SQLAlchemy 2.0 declarative base, registry, or a list of them or of mapped classes, for the Data
  panel (e.g. `models=Base`).

Other options are keyword arguments or environment variables, see [Settings](settings.md).

If `/sharpit` answers 404, see [Activation](activation.md).
