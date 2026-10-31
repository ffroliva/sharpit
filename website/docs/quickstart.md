# Quickstart

```python
from fastapi import FastAPI
import sharpit

app = FastAPI()

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

Keyword arguments for `sharpit.install()`:

- `engines`: optional sequence of SQLAlchemy `Engine` or `AsyncEngine` instances to monitor in connection pools and
  health checks (e.g. `engines=[engine]`). If omitted, engines are discovered automatically on first connection.
- `health_checks`: optional mapping of check names to zero-argument callables (e.g. `health_checks={"cache": ping_cache}`).
- `alembic_config`: optional path to `alembic.ini` (default `"alembic.ini"`).
- `settings`: optional pydantic-settings instance or sequence of instances to show configuration provenance.

Other options are keyword arguments or environment variables, see [Settings](settings.md).

If `/sharpit` answers 404, see [Activation](activation.md).
