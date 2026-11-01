# sharpit

[![CI](https://github.com/ffroliva/sharpit/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ffroliva/sharpit/actions/workflows/ci.yml)
[![Release](https://github.com/ffroliva/sharpit/actions/workflows/release.yml/badge.svg)](https://github.com/ffroliva/sharpit/actions/workflows/release.yml)
[![Quality Gate](https://sonarcloud.io/api/project_badges/measure?project=ffroliva_sharpit&metric=alert_status&branch=main)](https://sonarcloud.io/summary/overall?id=ffroliva_sharpit&branch=main)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=ffroliva_sharpit&metric=coverage&branch=main)](https://sonarcloud.io/component_measures?id=ffroliva_sharpit&metric=coverage&branch=main)

[![Reliability](https://sonarcloud.io/api/project_badges/measure?project=ffroliva_sharpit&metric=reliability_rating&branch=main)](https://sonarcloud.io/summary/overall?id=ffroliva_sharpit&branch=main)
[![Security](https://sonarcloud.io/api/project_badges/measure?project=ffroliva_sharpit&metric=security_rating&branch=main)](https://sonarcloud.io/summary/overall?id=ffroliva_sharpit&branch=main)
[![Maintainability](https://sonarcloud.io/api/project_badges/measure?project=ffroliva_sharpit&metric=sqale_rating&branch=main)](https://sonarcloud.io/summary/overall?id=ffroliva_sharpit&branch=main)
[![Duplication](https://sonarcloud.io/api/project_badges/measure?project=ffroliva_sharpit&metric=duplicated_lines_density&branch=main)](https://sonarcloud.io/component_measures?id=ffroliva_sharpit&metric=duplicated_lines_density&branch=main)

[![Python 3.12 | 3.13 | 3.14](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue.svg)](https://github.com/ffroliva/sharpit/blob/main/pyproject.toml)
[![Licence: Apache-2.0](https://img.shields.io/github/license/ffroliva/sharpit)](https://github.com/ffroliva/sharpit/blob/main/LICENSE)
[![Status: alpha](https://img.shields.io/badge/status-alpha-orange.svg)](https://github.com/ffroliva/sharpit/blob/main/CHANGELOG.md)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type checked: pyright](https://img.shields.io/badge/type%20checked-pyright-blue.svg)](https://github.com/microsoft/pyright)

<!-- CI and SonarCloud badges are live and pinned to main. Add the PyPI version badge with the first PyPI release. -->

An embedded, local-only developer console for FastAPI apps. One call mounts a web console at `/sharpit` and a
JSON API at `/sharpit/api` inside your own app, so a running service becomes understandable in minutes: its
configuration and where each value came from, every route, the dependency providers, loggers you can retune live,
and a vulnerability scan of the installed packages.

sharpit is a Python/FastAPI port of [BootUI](https://github.com/jdubois/boot-ui) by Julien Dubois (Apache-2.0), the
Spring Boot developer console. It ports BootUI's design goals, JSON contract and test cases; the UI is new.

![sharpit overview](https://raw.githubusercontent.com/ffroliva/sharpit/main/ui/tests/e2e/screenshots/overview-light.png)

> **Status: alpha (0.2.0, FastAPI only).** Django and Flask are not supported. See [CHANGELOG.md](https://github.com/ffroliva/sharpit/blob/main/CHANGELOG.md).

## Install

sharpit is not on PyPI yet. Install it from git:

```bash
pip install "sharpit @ git+https://github.com/ffroliva/sharpit.git"
# or
uv add "sharpit @ git+https://github.com/ffroliva/sharpit.git"
```

Python 3.12+. Runtime dependencies are only `starlette>=0.44` and `packaging>=23`. Optional extras:

| Extra | Adds | Why |
|---|---|---|
| `sharpit[fastapi]` | `fastapi>=0.115` | the supported host |
| `sharpit[settings]` | `pydantic-settings>=2.4` | the Config panel shows which source each value came from |

## Quickstart

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

Other options are keyword arguments or environment variables, see [Settings](https://ffroliva.github.io/sharpit/settings/).

If `/sharpit` answers 404, read [Activation](https://ffroliva.github.io/sharpit/activation/): sharpit stays off unless a dev signal turns it on.

## Gate CI on findings

sharpit turns runtime capture into automated test gates with `pytest --sharpit`. It tracks SQL
statements and observable exceptions per test, detects N+1 queries, checks query budgets, and runs
static analysis advisors. If a test exceeds its query budget, triggers an N+1 query, or swallows an
unhandled exception, the build fails. When capture cannot see enough to judge, the run status is
`unknown` and fails closed.

```bash
pytest --sharpit --sharpit-report=sharpit-report.json --sharpit-junit=sharpit-junit.xml
```

Read [Pytest plugin](https://ffroliva.github.io/sharpit/pytest-plugin/) and [Test report](https://ffroliva.github.io/sharpit/report/) for options, gates, and CI examples.

## Documentation

The full documentation is at **<https://ffroliva.github.io/sharpit/>**:

- [Activation](https://ffroliva.github.io/sharpit/activation/): when sharpit turns on, and why a plain `uvicorn app:app` gives 404
- [Panels](https://ffroliva.github.io/sharpit/panels/): what each panel shows
- [Pytest plugin](https://ffroliva.github.io/sharpit/pytest-plugin/): CI gates for queries, N+1, exceptions, and advisors
- [Test report](https://ffroliva.github.io/sharpit/report/): the `sharpit-report/1` JSON schema and JUnit XML
- [SQL sources](https://ffroliva.github.io/sharpit/sql-sources/): tracing SQLAlchemy and raw `sqlite3`
- [MCP for AI agents](https://ffroliva.github.io/sharpit/mcp/): the read-only MCP endpoint and its 18 tools
- [Settings](https://ffroliva.github.io/sharpit/settings/): every environment variable and `install()` keyword
- [Safety model](https://ffroliva.github.io/sharpit/safety/): local-only guard, tokens, masking, proxies and workers
- [How it works](https://ffroliva.github.io/sharpit/how-it-works/) and [Deviations from BootUI](https://ffroliva.github.io/sharpit/deviations/)

## License

Apache License 2.0. See [LICENSE](https://github.com/ffroliva/sharpit/blob/main/LICENSE) and [NOTICE](https://github.com/ffroliva/sharpit/blob/main/NOTICE). sharpit is derived from
[BootUI](https://github.com/jdubois/boot-ui), Copyright Julien Dubois.
