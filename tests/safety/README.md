# tests/safety: per-lane safety rows

Each 0.4 panel lane adds `tests/safety/test_<lane_id>_safety.py` (lane id in lower case with `_`, e.g.
`test_a_data_safety.py`) and never edits `tests/test_safety_matrix.py` or `tests/conftest.py`. The file exports:

```python
PANEL = "data"  # the panel id (a 0.4 id or sql-trace) whose flag gates these rows; omit it for base-route tests
GET_ROWS = ["/sharpit/api/data", "/sharpit/api/data/{table}"]  # every GET route path format the panel adds
WRITE_ROWS = [("POST", "/sharpit/api/data/query")]  # every POST/PUT/PATCH/DELETE route as (method, path format)
PATH_PARAMS = {"table": "orders"}  # a sample value for each new path parameter
```

While `PANEL` is implemented, `tests/test_safety_matrix.py` feeds these rows into the same sweeps as its base rows: the
GET and write route tables must equal the live routes, every route under the panel's prefix answers 403 when the
panel is disabled, every write answers 403 under global and per-panel read-only (so a panel with writes must be
`actionCapable`), and every GET runs under `no_side_effects`. Convertors (`{name:path}`) are stripped before comparing.
A file with a bad `PANEL` or row shape fails the route-table tests naming it; a file that cannot import (or skips at
module level) adds no rows and is named when the live table then shows an undocumented route. The same file holds the
lane's own safety tests.
