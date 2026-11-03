# FastAPI advisor checks

The `fastapi` advisor (BootUI's `spring` advisor, re-cut for FastAPI) runs on `POST /sharpit/api/fastapi/scan` or
`sharpit fastapi scan`. It reads the application's own source with `ast` (never imports or executes it) and a few
attributes of the application object, and reports review prompts, not verdicts. `SPRING-*` ids keep BootUI's id where
the concept maps; `FASTAPI-*` ids are new.

A route handler is analysed only when it is a plain Python function defined inside the application package, after
unwrapping `functools.wraps` decorators. Callable instances, `functools.partial` objects, builtins and library
functions are skipped and named in the report's limitations.

| id | severity | category | title |
|---|---|---|---|
| FASTAPI-ASYNC-001 | INFO | Performance and concurrency | Review blocking work in sync endpoints |
| FASTAPI-ASYNC-002 | HIGH | Performance and concurrency | Blocking call inside an async endpoint |
| FASTAPI-HTTP-001 | LOW | Web and HTTP | Outbound HTTP call without a timeout |
| FASTAPI-BG-001 | LOW | Performance and concurrency | Review heavy work in BackgroundTasks |
| FASTAPI-PYD-001 | MEDIUM | Configuration | Pydantic v1 API in use |
| FASTAPI-RESP-001 | LOW | Web and HTTP | Endpoint returns a dict without a response model |
| FASTAPI-EVT-001 | LOW | Configuration | Deprecated on_event startup and shutdown handlers |
| FASTAPI-EXC-001 | MEDIUM | Web and HTTP | Broad except swallows errors in an endpoint |
| SPRING-WEB-004 | MEDIUM | Web and HTTP | Review configured fallback error details |
| SPRING-CONFIG-004 | INFO | Configuration | Consider a stable application name |

Not yet (parked for a later lane): `FASTAPI-ASYNC-003` (async endpoint on a sync database session),
`FASTAPI-ASYNC-004` (threadpool capacity), `FASTAPI-DEP-001` (dependency overrides left in place), `SPRING-WEB-001`
(no response compression), `SPRING-CONFIG-002` (root logger at DEBUG), `SPRING-DATA-001` (in-memory SQLite with a
production-like profile).
