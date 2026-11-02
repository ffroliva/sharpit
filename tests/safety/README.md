# tests/safety: per-lane safety rows

Each 0.4 panel lane adds `tests/safety/test_<lane_id>_safety.py` (lane id in lower case with `_`, e.g.
`test_a_data_safety.py`) and never edits `tests/test_safety_matrix.py`. The file exports:

```python
PANEL = "data"  # the sharpit panel id whose panels04 flag gates these rows
GET_ROWS = ["/sharpit/api/data", "/sharpit/api/data/{name}"]  # every GET route path format the panel adds
WRITE_ROWS = [("POST", "/sharpit/api/data/query")]  # every POST/DELETE route as (method, path format)
```

The matrix's route-table tests include these rows only while `PANEL` is implemented. A path parameter needs a sample
value in `tests/conftest.py::_PATH_PARAMS`. The same file holds the lane's own safety tests (`no_side_effects` on every
GET, panel-disabled 403, read-only denial for each write).
