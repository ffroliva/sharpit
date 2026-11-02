# Lane F-rest findings

## Red table (gate format)

| Test id | Red SHA | Assertion message | Disposition |
|---|---|---|---|
| `tests/test_surface_follows_flags.py::test_catalogue_rebuild_is_idempotent_for_a_panel_implemented_at_import` | `7b43c180dcf5313c9e50ef198a9060c6ef30da83` | `assert error is None` | Fixed in `6001f62` |
| `tests/test_safety_lane_rows.py::test_lane_rows_complete_the_route_tables` | `7b43c180dcf5313c9e50ef198a9060c6ef30da83` | `assert safety.route_formats(app, WRITE) - before_writes - lane_writes == set()` | Fixed in `6001f62` |
| `tests/scripts/test_lane_gate.py::test_lane_gate_replay_syncs_the_test_extra` | `7b43c180dcf5313c9e50ef198a9060c6ef30da83` | `assert calls[0][:7] == ["uv", "run", "--project", str(tmp_path), "--frozen", "--extra", "test"]` | Fixed in `6001f62` |

## Findings

1. `tests/test_surface_follows_flags.py` fixture merged lane tools into the current `tools.TOOLS`, so a panel already implemented at import raised the duplicate-tool `ValueError`. Fixed: `tests/surface.py::catalogue_with_lanes` builds from `tools._BASE_TOOLS`/`_BASE_COMMANDS`.
2. The shared route-table tests forced every panel lane to edit `tests/test_safety_matrix.py`. Fixed: rows come from implemented panels' `tests/safety/test_<lane_id>_safety.py` (`PANEL`, `GET_ROWS`, `WRITE_ROWS`) via `tests/safety/__init__.py::lane_rows`; base rows stay literal. Controls: `tests/test_safety_lane_rows.py::test_route_without_a_lane_row_is_named`, `::test_lane_rows_of_an_unimplemented_panel_are_ignored`.
3. `lane_gate.py` replay ran `uv run --project <integration> --frozen`, which syncs without the test extra. Fixed: `--frozen --extra test`.
