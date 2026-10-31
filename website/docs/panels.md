# Panels

| Panel | What it shows |
|---|---|
| Overview | app, Python and package versions, active profiles, activation reason and warnings |
| Configuration | environment, `.env` files, pydantic-settings and `os.getenv` keys, the winning source of each value, masked |
| Mappings | every route of the host app |
| Loggers | logger tree with levels you can change at runtime |
| Beans | dependency providers, middleware and lifespan, with their dependencies |
| Vulnerabilities | installed distributions checked against [OSV](https://osv.dev) and scored with EPSS, on explicit request |
| HTTP Exchanges | ring buffer of recent HTTP requests with duration, headers, status code, and path masking |
| Exceptions | unhandled errors grouped by exception class and innermost application frame |
| SQL Trace | executed SQL statements, execution durations, slow query alerts, and live SSE feed |
| Live Activity | correlated timeline of requests, SQL queries, and exceptions, with N+1 query detection |
| Log Tail | recent log records and live SSE feed with resumption token |
| Alembic | read-only database migration status and pending versions |
| Database Pools | SQLAlchemy engine connection pool sizes, checkouts, and overflow status |
| Health | status of registered database engines and custom health checks |
| Threads | thread dump and running asyncio tasks with request correlation |
| REST API Advisor | static inspection of FastAPI route signatures for API design violations |
| HTTP Probe | in-process HTTP request execution against local routes without external network calls |
| MCP server | status and switch for the read-only MCP endpoint |
| CLI | the same tool catalogue over plain HTTP (`POST /sharpit/api/cli/tools/<tool>`) |

`GET /sharpit/api/panels` lists what this build offers and why a panel is unavailable or read-only.

![sharpit configuration panel](https://raw.githubusercontent.com/ffroliva/sharpit/main/ui/tests/e2e/screenshots/config-light.png)
