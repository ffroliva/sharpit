# BootUI → Python: panel-by-panel mapping

Working draft (2026-10-30). For each BootUI panel group (`/bootui/api/**`), this lists where the same data lives
in FastAPI/Starlette, Django and Flask, and which reference project in this folder already does something similar.

Portability: **P** = ports directly · **A** = needs an adapter per framework · **X** = no Python counterpart (drop) ·
**N** = Python-only, new.

## Overview & runtime

| BootUI panel | Python source | Port | Prior art here |
|---|---|---|---|
| overview | `sys.version`, `platform`, `importlib.metadata.distributions()`, server (uvicorn/gunicorn/granian) | P | tidewave, pyctuator `/info` |
| health | `engine.connect()` / `django.db.connections`, cache ping, broker ping | A | pyctuator `/health` |
| metrics | `prometheus_client.REGISTRY`, OpenTelemetry meter provider if present | P | pyctuator `/metrics` |
| threads | `threading.enumerate()` + `sys._current_frames()` | P | pyctuator `/threaddump` |
| live-memory, heap-dump | `tracemalloc` snapshots, `gc.get_stats()`, `psutil` | P | – |
| startup | import timing (`-X importtime` style), app factory / lifespan timing | A | – |
| jvm-tuning, graalvm, crac | – | X | – |
| **asyncio tasks** | `asyncio.all_tasks()` with stacks, loop lag, `slow_callback_duration` | **N** | – |
| **interpreter** | GIL / free-threaded build (`sys._is_gil_enabled`), Python EOL, worker count/class | **N** | – |

## Configuration

| BootUI panel | Python source | Port | Prior art |
|---|---|---|---|
| config (+ source provenance) | pydantic-settings `BaseSettings` sources (init/env/.env/secrets); Django `settings` vs `global_settings` (what `diffsettings` does); Flask `app.config` (no provenance, needs a wrapper) | A | django-debug-toolbar Settings panel, pyctuator `/env` |
| profile-diff | diff of `.env.*` files / alternative `DJANGO_SETTINGS_MODULE` | A | – |
| loggers (read + change level) | `logging.root.manager.loggerDict` | P | pyctuator `/loggers` |
| beans / dependency graph | FastAPI `route.dependant` tree + `dependency_overrides`; Django `apps.get_app_configs()`, `MIDDLEWARE`, signal receivers; Flask `app.extensions`, blueprints, request hooks | A | – (**gap**) |
| conditions | no auto-config analogue | X | – |
| mappings | FastAPI `app.routes` + `app.openapi()`; Django `get_resolver()` walk; Flask `app.url_map.iter_rules()` | A | tidewave (routes tool), pyctuator fork `/mappings` |

## Database

| BootUI panel | Python source | Port | Prior art |
|---|---|---|---|
| sql-trace | SQLAlchemy `before/after_cursor_execute`; Django `connection.execute_wrapper` | A | django-debug-toolbar SQL, fastapi-debug-toolbar, django-silk |
| hibernate-statistics, hibernate | SQLAlchemy session/identity-map stats; N+1 detection | A | silk (query counts) |
| database-connection-pools | `engine.pool.status()`, psycopg_pool stats, Django `CONN_MAX_AGE` | A | – |
| transactions | SQLAlchemy `after_begin/commit/rollback`; Django `atomic` hooks | A | – |
| data (Spring Data) | `apps.get_models()`, SQLAlchemy `registry.mappers` | A | tidewave `get_models` |
| flyway, liquibase | Alembic current vs script heads; Django `MigrationExecutor` (applied vs pending) | A | – |
| postgresql, mysql, database-advisor | same SQL against `pg_stat_statements` / `performance_schema`, so **ports directly** | P | – |

## Diagnostics & activity

| BootUI panel | Python source | Port | Prior art |
|---|---|---|---|
| activity, traces, http-exchanges | ASGI/WSGI middleware ring buffer; OTel in-memory span processor | A | silk, debug toolbars, Spotlight |
| per-request profiler | pyinstrument | P | fastapi-debug-toolbar (profiling panel), silk |
| exceptions | framework exception handlers + `sys.excepthook` + logging capture | A | Spotlight |
| log-tail | `logging.Handler` ring buffer | P | fastpanel |
| http-probe | `httpx` against the app's own routes | P | – |
| rest-client-trace | `httpx` event hooks/transport, `requests` adapter, OTel instrumentation | A | – |

## Services

| BootUI panel | Python source | Port |
|---|---|---|
| scheduled | APScheduler `get_jobs()`, Celery beat schedule, RQ | A |
| fault-tolerance | tenacity / pybreaker (thin) | A |
| websockets | Starlette `WebSocket`, Django Channels | A |
| cache | Django `caches`, redis-py `INFO`, cachetools | A |
| kafka, rabbitmq | aiokafka / confluent-kafka, aio-pika / pika, Celery/kombu | A |
| jms | – | X |
| email | Django locmem/console backends, fastapi-mail | A |
| ai | anthropic / openai / pydantic-ai / LangChain over httpx hooks (relevant to KliperMedia and gflow-cli) | A |
| http-sessions | Django session backend, Starlette `SessionMiddleware` | A |

## Security & advisors

| BootUI panel | Python source | Port |
|---|---|---|
| spring-security, security | Django auth/CSRF/`SECURE_*` + **`manage.py check --deploy`** (a ready-made rule source); FastAPI security deps found in the `Depends` tree, `CORSMiddleware` config | A |
| security-logs | `django.security.*` loggers | A |
| vulnerabilities | installed distributions → OSV querybatch (what pip-audit does); BootUI's EPSS and fix-availability logic ports as is | P |
| pentesting | route-based checks over the mappings | P |
| rest-api advisor | rules over the OpenAPI document (FastAPI produces it natively) | P |
| architecture advisor | import graph via grimp / import-linter contracts | A |
| spring / quarkus advisors | → Django `django.core.checks` + FastAPI-specific rules (sync `def` endpoints on the threadpool, blocking calls in `async def`, Pydantic v1 leftovers) | A/N |
| **dependency drift** | `uv.lock` / `requirements*.txt` vs `importlib.metadata` | **N** |

## Developer tools

| BootUI panel | Python source | Port |
|---|---|---|
| mcp, mcp-server | official `mcp` Python SDK, same masked read-only tools (no `eval`, unlike Tidewave) | P |
| cli | same command shape; Python client over `/…/api` | P |
| devtools | uvicorn `--reload` / Django autoreloader status | A |
| dev-services | testcontainers-python / docker compose status | A |
| github, copilot, claude-code | language-agnostic | P |

## Takeaways

1. Roughly 70% of the panels have a direct Python counterpart. About 10 are JVM-only (conditions, GraalVM, CRaC,
   JVM tuning, Hibernate internals, JMS) and get dropped.
2. The reusable assets are the **Vue UI**, if the JSON contract stays compatible; the **DB operational SQL**; the
   **OSV/EPSS vulnerability logic**; and the **advisor and safety model** (masking, fail-closed activation, no
   side effects on render).
3. Nothing in the reference projects covers the **beans / dependency graph** equivalent, **effective config with
   provenance**, or **advisors**. That is the gap.
4. The adapter layer has to cover ASGI (FastAPI/Starlette) and WSGI (Flask/Django), and Django is closer to
   Spring's "everything registered in one place" model than FastAPI is.
5. gflow-cli has no long-running server. It would need a "run and report" mode (wrap a run, collect the same
   data, write a report) rather than an embedded console.
