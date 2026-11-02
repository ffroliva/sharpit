# Lane F-rest handoff

Implementer: claude-subagent-opus (lane F-rest)

Status: done. Base `4a47fe2` (`release/0.4.0`), head `6001f62`. Red `7b43c18`, fix `6001f62`. The diff touches `scripts/dev/lane_gate.py` (coordinator passes `--allow-path scripts/dev/lane_gate.py`).

## Verification

- Full suite (`uv run pytest -q -n 4`): 3759 passed, 5 skipped, 2 failed; the failures are the request and SQL-statement overhead budgets in a 705 s run on a heavily loaded machine; F-rest changes no src/ file (git diff --stat 4a47fe2 HEAD -- src is empty), budgets not raised.
- `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`: clean.
- `UV_LINK_MODE=copy` is needed for every `uv` command on this machine (hardlink error 1142).

## Interface for panel lanes

Panel lanes: add `tests/safety/test_<lane_id>_safety.py` (lane id lower case with `_`, e.g. `test_a_data_safety.py`) exporting `PANEL = "<sharpit panel id>"`, `GET_ROWS = ["/sharpit/api/<id>", ...]` (every GET route path format your `fastapi/routes/<id>.py` adds, `{param}` placeholders allowed: give each new param a sample value in `tests/conftest.py::_PATH_PARAMS`) and `WRITE_ROWS = [("POST", "/sharpit/api/<id>/..."), ...]` (every POST/DELETE route as `(method, path format)`). `tests/test_safety_matrix.py::test_get_route_table_is_complete` / `::test_write_route_table_is_complete` include those rows only while your `panels04` flag is true, so never edit the shared matrix; put your own safety tests (`no_side_effects` on GETs, panel-disabled 403, read-only denial per write) in the same file. Shared count tests derive from your flag via `tests/surface.py` (no edits); in tests that rebuild the tool catalogue use `surface.catalogue_with_lanes(*panels04.tool_definitions())` (built from the base catalogue, so it is idempotent when your flag is already on).

| Symbol | Contract |
|---|---|
| `tests/safety/__init__.py::lane_rows(root=HERE)` | `-> tuple[set[str], set[tuple[str, str]]]`: GET path formats and `(method, path format)` writes from every `test_*_safety.py` whose `PANEL` is implemented. |
| `tests/safety/__init__.py::route_formats(app, methods)` | `-> set[tuple[str, str]]`: `(method, "/sharpit" + path format)` of the installed sub-app's routes. |
| `tests/surface.py::catalogue_with_lanes(lane_tools, lane_commands)` | `-> (TOOLS, COMMANDS)` from the base catalogue plus the lane tools; idempotent. |

## Red-test replay table

| Test id | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| `tests/test_surface_follows_flags.py::test_catalogue_rebuild_is_idempotent_for_a_panel_implemented_at_import` | `7b43c180dcf5313c9e50ef198a9060c6ef30da83` | `assert error is None` | Fixed in `6001f62` |
| `tests/test_safety_lane_rows.py::test_lane_rows_complete_the_route_tables` | `7b43c180dcf5313c9e50ef198a9060c6ef30da83` | `assert safety.route_formats(app, WRITE) - before_writes - lane_writes == set()` | Fixed in `6001f62` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_replay_syncs_the_test_extra` | `7b43c180dcf5313c9e50ef198a9060c6ef30da83` | `assert calls[0][:7] == ["uv", "run", "--project", str(tmp_path), "--frozen", "--extra", "test"]` | Fixed in `6001f62` |
