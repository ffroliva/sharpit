# Lane F-rest findings

## Red table (gate format)

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

## Findings

1. `tests/test_surface_follows_flags.py` fixture merged lane tools into the current `tools.TOOLS`, so a panel already implemented at import raised the duplicate-tool `ValueError`. Fixed: `tests/surface.py::catalogue_with_lanes` builds from `tools._BASE_TOOLS`/`_BASE_COMMANDS`.
2. The shared route-table tests forced every panel lane to edit `tests/test_safety_matrix.py`. Fixed: rows come from implemented panels' `tests/safety/test_<lane_id>_safety.py` (`PANEL`, `GET_ROWS`, `WRITE_ROWS`) via `tests/safety/__init__.py::lane_rows`; base rows stay literal. Controls: `tests/test_safety_lane_rows.py::test_route_without_a_lane_row_is_named`, `::test_lane_rows_of_an_unimplemented_panel_are_ignored`.
3. `lane_gate.py` replay ran `uv run --project <integration> --frozen`, which syncs without the test extra. Fixed: `--frozen --extra test`.
4. Round 1 (code review): lane rows now feed the read-only, disabled-panel and GET sweeps; lane files import as `safety.<stem>` (cached), a skip or import error is reported instead of raised, `PANEL` is optional but must be a per-panel-module id, rows are validated and convertors stripped, lanes may export `PATH_PARAMS`, `safety.route_formats` is gone, the catalogue check runs in a fresh interpreter, and the gate comment states the real cause. Red `0e10338`, fix `6c5e9eb`.

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

5. Round 2 (coordinator): the flag-flip proof plants on the first still-unimplemented 0.4 panel (skips when none) and checks membership against `tests/surface.py`'s expectations (red `a949929`, fix `4f1ba74`); a lane's `PATH_PARAMS` apply only to its own rows, never to base routes (red `76dc47f`, fix `70f6932`).
