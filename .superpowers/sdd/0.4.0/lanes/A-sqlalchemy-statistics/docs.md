# User-facing text for the owner (O3)

- Panel `sqlalchemy-statistics` (BootUI `hibernate-statistics`): SQL statement counts from SQL Trace's lifetime totals,
  the slowest statement, and N+1 candidates per route. ORM session/entity counters are `null` with a reason.
- SKILL row: `sqlalchemy-statistics` — "statement counts and N+1 per route from the SQL recorder; no ORM counters".
- Rename: BootUI `hibernate-statistics` is `sqlalchemy-statistics` in sharpit (API path, MCP `get_sqlalchemy_statistics`,
  CLI `sqlalchemy-statistics`, env `SHARPIT_PANELS_SQLALCHEMY_STATISTICS_*`).
