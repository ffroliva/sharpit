# sharpit
Embedded, local-only developer console for Python apps (FastAPI, Django, Flask): make a running app understandable in minutes.

## Requirements

Python 3.12+. Runtime dependencies: `starlette>=0.40`, `packaging>=23`. The `test` extra pins these floors (checked in CI with `--resolution lowest-direct`): `fastapi>=0.115`, `pydantic-settings>=2.4`, `uvicorn>=0.30`, `httpx>=0.27`, `pytest>=8`, `pytest-timeout>=2.3`.
