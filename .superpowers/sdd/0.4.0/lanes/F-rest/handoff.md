# Lane F-rest handoff

Implementer: claude-subagent-opus (lane F-rest)

Status: done. Base `4a47fe2` (`release/0.4.0`), head `6c5e9eb`. Red `7b43c18`, fix `6001f62`; round 1 red `0e10338`, fix `6c5e9eb`. The diff touches `scripts/dev/lane_gate.py` (coordinator passes `--allow-path scripts/dev/lane_gate.py`).

## Verification

- Full suite (`uv run pytest -q -n 4`): 3763 passed, 5 skipped, 2 failed; the failures are the request and SQL-statement overhead budgets in a 923 s run on a heavily loaded machine; F-rest changes no src/ file, budgets not raised.
- `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`: clean.
- `UV_LINK_MODE=copy` is needed for every `uv` command on this machine (hardlink error 1142).

## Interface for panel lanes

Panel lanes: add `tests/safety/test_<lane_id>_safety.py` (lane id lower case with `_`, e.g. `test_a_data_safety.py`; never edit `tests/test_safety_matrix.py` or `tests/conftest.py`) exporting `PANEL = "<panel id>"` (your 0.4 id, or `sql-trace` for A-sqltrace-insights; omit `PANEL` in a file that only tests base routes), `GET_ROWS = ["/sharpit/api/<id>", "/sharpit/api/<id>/{param}", ...]` (every GET route path format your `fastapi/routes/<id>.py` adds; `{name:path}` convertors are fine), `WRITE_ROWS = [("POST", "/sharpit/api/<id>/..."), ...]` (every POST/PUT/PATCH/DELETE route as `(method, path format)`) and `PATH_PARAMS = {"param": "sample"}` (a sample value for each new path parameter). While your `panels04` flag is true the shared matrix feeds these rows into the same sweeps as its base rows: the GET and write route tables must equal your live routes, every route under your prefix answers 403 when the panel is disabled, every write answers 403 under global and per-panel read-only (so a panel with writes must be `actionCapable` in `PANELS`), and every GET runs under `no_side_effects`. A bad `PANEL` or row shape fails the route-table tests naming your file; a file that cannot import or skips at module level adds no rows and is named when the live table then shows an undocumented route. Put your own safety tests in the same file. Shared count tests follow your flag via `tests/surface.py` (no edits); a test that rebuilds the tool catalogue uses `surface.catalogue_with_lanes(*panels04.tool_definitions())`.

| Symbol | Contract |
|---|---|
| `tests/safety/__init__.py::load(package="safety")` | `-> Lanes(implemented, invalid, unimportable, params)`; imports each `test_*_safety.py` as `safety.<stem>`. |
| `safety.write_cases(base, lanes, params)` / `get_rows(lanes, params)` / `write_rows(lanes)` | the matrix's sweep inputs: base rows plus implemented lanes' rows. |
| `safety.live_write_routes(app, exempt)` | `(method, "/sharpit" + path format)` of every write route (the one copy). |
| `tests/surface.py::catalogue_with_lanes(lane_tools, lane_commands)` | `(TOOLS, COMMANDS)` from the base catalogue plus the lane tools; idempotent. |

## Red-test replay table

| Test id | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| `tests/scripts/test_lane_gate.py::test_lane_gate_replay_syncs_the_test_extra` | `7b43c180dcf5313c9e50ef198a9060c6ef30da83` | `assert calls[0][:7] == ["uv", "run", "--project", str(tmp_path), "--frozen", "--extra", "test"]` | Fixed in `6001f62` |
| `tests/test_safety_lane_sweeps.py::test_lane_write_row_reaches_the_read_only_sweep` | `0e1033829f7325305fbf70eaa7bdd1e4b0aa7197` | `assert ("data", "POST", "/sharpit/api/data/probe", None) in cases` | Fixed in `6c5e9eb` |
| `tests/test_safety_lane_sweeps.py::test_lane_rows_cover_the_live_write_table` | `0e1033829f7325305fbf70eaa7bdd1e4b0aa7197` | `assert uncovered == set()` | Fixed in `6c5e9eb` |
| `tests/test_safety_lane_sweeps.py::test_lane_file_loads_as_a_package_module` | `0e1033829f7325305fbf70eaa7bdd1e4b0aa7197` | `assert safety.write_rows(lanes) == {("POST", "/sharpit/api/data/probe")}` | Fixed in `6c5e9eb` |
| `tests/test_safety_lane_sweeps.py::test_lane_file_that_skips_or_fails_is_reported_not_raised` | `0e1033829f7325305fbf70eaa7bdd1e4b0aa7197` | `assert [line.split(":")[0] for line in lanes.unimportable] == ["test_a_skip_safety.py", "test_b_broken_safety.py"]` | Fixed in `6c5e9eb` |
| `tests/test_safety_lane_sweeps.py::test_panel_is_optional_but_must_be_a_known_id` | `0e1033829f7325305fbf70eaa7bdd1e4b0aa7197` | `assert [line.split(":")[0] for line in lanes.invalid] == ["test_x_safety.py"]` | Fixed in `6c5e9eb` |
| `tests/test_safety_lane_sweeps.py::test_row_shapes_are_validated_and_convertors_stripped` | `0e1033829f7325305fbf70eaa7bdd1e4b0aa7197` | `assert [lane.gets for lane in lanes.implemented] == [("/sharpit/api/data/{name}",)]` | Fixed in `6c5e9eb` |
| `tests/test_surface_follows_flags.py::test_shared_counts_follow_a_flip_of_any_unimplemented_panel[data-postgresql-implemented]` | `a949929f2b439b6924374e23f3bd1cbc44ca6da0` | `assert plant not in already` | Fixed in `4f1ba74` |
| `tests/test_safety_lane_sweeps.py::test_lane_path_params_apply_only_to_that_lanes_rows` | `76dc47f8512c5a2e3428374712b10279e17216d0` | `assert base_path == "/sharpit/api/database-connection-pools/pools/nope/snapshot"` | Fixed in `70f6932` |

## Superseded reds (test deleted; its row left the red table)

| Test | Historical SHA | Why |
|---|---|---|
| test_safety_lane_rows.py::test_lane_rows_complete_the_route_tables | was 7b43c18 | replaced by `test_safety_lane_sweeps.py::test_lane_rows_cover_the_live_write_table` and `::test_matrix_feeds_lane_rows_into_its_sweeps` (round 1 item 7: `safety.route_formats` deleted, real matrix wiring) |
| test_surface_follows_flags.py::test_catalogue_rebuild_is_idempotent_for_a_panel_implemented_at_import | was 7b43c18 | replaced by `::test_catalogue_rebuild_matches_the_import_time_catalogue_with_the_flag_on` (round 1 item 8: a fresh interpreter re-imports `sharpit.engine.tools` with the flag on; no catalogue patching) |
| test_surface_follows_flags.py::test_every_shared_count_follows_a_flag_flip | was aaa97d8 (lane F) | replaced by `::test_shared_counts_follow_a_flip_of_any_unimplemented_panel`: it planted on `data` and asserted `[-1]` positions, which break once real lanes implement panels |

## Not a red (replacement or wiring tests that pass on arrival)

- `tests/test_safety_lane_sweeps.py::test_matrix_feeds_lane_rows_into_its_sweeps`: checks the matrix's own `ALL_WRITES` and `test_write_route_table_is_complete` with a planted lane (removing the lane union there fails it).
- `tests/test_surface_follows_flags.py::test_catalogue_rebuild_matches_the_import_time_catalogue_with_the_flag_on`: replacement for the superseded idempotency red; the behaviour was already fixed in `6001f62`.
- `tests/test_safety_lane_rows.py::test_route_without_a_lane_row_is_named` and `::test_lane_rows_of_an_unimplemented_panel_are_ignored`: deleted with that file (controls, never reds).
