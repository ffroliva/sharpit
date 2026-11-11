# tests/safety: per-lane safety rows

Each 0.4 panel lane adds `tests/safety/test_<lane_id>_safety.py` (lane id in lower case with `_`, e.g.
`test_a_data_safety.py`) and never edits `tests/test_safety_matrix.py` or `tests/conftest.py`, except that base-route rows
belong in `tests/test_safety_matrix.py`. The file exports:

```python
PANEL = "data"  # the panel id (a 0.4 id or sql-trace) whose flag gates these rows; omit it for base-route tests
GET_ROWS = ["/sharpit/api/data", "/sharpit/api/data/{table}"]  # every GET route path format the panel adds
WRITE_ROWS = [("POST", "/sharpit/api/data/query")]  # every POST/PUT/PATCH/DELETE route as (method, path format)
PATH_PARAMS = {"table": "orders"}  # samples for this file's own rows only (base routes keep conftest's)
CLI_ACTIONS = ["data_export"]  # the panel's CLI-only action tools (refused when gated, never on MCP)
TOOL_ARGS = {"get_data_rule_violations": lambda handle: {...}}  # MCP tool -> its arguments over the installed app
TOOL_SEEDS = {"get_data_rule_violations": lambda ctx: {...}}  # the same over test_tools.py's bare SharpitContext
```

`TOOL_ARGS` and `TOOL_SEEDS` are for MCP tools with required arguments, e.g. an advisor's
`get_<advisor>_rule_violations`, which needs `{"id", "scanId"}` from a scan: the callable runs that advisor's scan
through its service and returns the arguments. `TOOL_ARGS` callables take the installed `SharpitHandle`
(`test_every_mcp_tool_no_side_effects`); `TOOL_SEEDS` callables take `tests/engine/test_tools.py`'s bare
`SharpitContext`, which has no routes, so they seed what the tool reads first (`test_mcp_tools_no_side_effects`).
Keys must be MCP tool names and values callables, or the file is refused like a bad row. The base panels' own
declarations (`BASE_TOOL_ARGS`, `BASE_TOOL_SEEDS` in `__init__.py`, rest-api today) take the same path. The GET sweep
lets every `/sharpit/api/<panel>/rules/{id}/violations` route answer 400 without `scanId`, but only with the
contract's `{"error": "Advisor scan ID must not be blank."}`; `/sharpit/api/metrics/detail` may also answer 400
without `name`, but only with BootUI's `{"error": "Metric name must not be blank"}`; every other GET answers 200, 307 or 404.

While `PANEL` is implemented, `tests/test_safety_matrix.py` feeds these rows into the same sweeps as its base rows: the
GET and write route tables must equal the live routes, every route under the panel's prefix answers 403 when the
panel is disabled, every write answers 403 under global and per-panel read-only (so a panel with writes must be
`actionCapable`), and every GET runs under `no_side_effects`. Convertors (`{name:path}`) are stripped before comparing.
A file with a bad `PANEL` or row shape fails the route-table tests naming it; a file that cannot import (or skips at
module level) adds no rows and is named when the live table then shows an undocumented route. The same file holds the
lane's own safety tests.

## W8 write rows (example)

A W8 action lane (`tests/safety/test_w8_<lane>_safety.py`) documents only its own actions. A panel with a per-panel
module (`cache`, `dev-services`) declares them as rows; the panel is already `actionCapable` (lane A0), so the matrix
proves the read-only refusal for every row:

```python
PANEL = "cache"
GET_ROWS = []  # the read side's GETs stay in the read lane's file
WRITE_ROWS = [("POST", "/sharpit/api/cache/clear")]
```

`config` and `alembic` are base panels with no per-panel module, so a `PANEL` naming them is refused; their write
routes go into `WRITES` in `tests/test_safety_matrix.py` (one row per route, with the panel id) and the lane file keeps
`PANEL` unset. Either way the lane file also holds one refusal test per gate (inactive 404, guard, panel disabled 403,
global and panel read-only 403 `PANEL_READ_ONLY`, the action's own setting or confirmation), each asserting the
action's handler spy recorded zero calls.
