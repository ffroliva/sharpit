# Lane D3: 2.2.0 DB & Runtime Panels Drift (`alembic`, `database-connection-pools`, `health`, `threads`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- **Lane ID:** `D3`
- **Evidence folder:** `.superpowers/sdd/0.4.0/lanes/D3/`
- **Goal:** Align `database-connection-pools` (`poolLibraryPresent`, `implementation`, nullable `readOnly`/`autoCommit`), `threads` (`McpAgentViews.INVENTORY_DEFAULT_LIMIT = 25`), `alembic`, and `health` with the BootUI 2.2.0 contract and golden fixtures.
- **Spec sections:** §9 D3 (best effort 12), §6.1 (definition of done), §10.2, §10.3 (lane gate); contract `docs/reference/BOOTUI-CONTRACT-0.4-DRIFT.md` §§15–18.
- **Worker profile:** **S**, **mechanical** (localized DTO key renames, nullable field alignment, and MCP default limit; default worker in `PLAN.md`: `agy`).
- **Depends on:** `D1` (`PLAN.md` line 92; `F` is transitive via `D1`).
- **Foundation interfaces consumed (`F-foundation.md` §"Foundation consumer interface table"):**
  - `sharpit.fastapi.routes.<id>` (`pools`, `alembic`, `health`, `threads`) and `sharpit.fastapi.adapter` (calls `pools_report(ctx)` at `adapter.py:431`)
  - `sharpit.engine.sqla.sqlalchemy_module` (`def sqlalchemy_module() -> Any | None`)
  - `sharpit.engine.collectors.pools.pools_report` (`def pools_report(ctx: SharpitContext) -> dict[str, Any]` and `def _pool_dto(ctx: SharpitContext, name: str, engine: Any) -> dict[str, Any]`)
  - `sharpit.engine.tool_stubs.<id>` (`threads`) and `sharpit.engine.tools` (`_build_registry`, `execute_tool`)
  - `tests.golden.assert_parity` (`def assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None` + `tests/fixtures/bootui/2.2.0/ids.json`)
  - `tests/safety/` and `tests/masking/` packages (`tests/safety/test_d3_safety.py`, `tests/masking/test_d3_masking.py`)
  - `scripts/dev/lane_gate.py` (`python scripts/dev/lane_gate.py D3`)
- **Files this lane MAY touch:**
  - `src/sharpit/engine/collectors/pools.py`
  - `src/sharpit/engine/collectors/alembic.py`
  - `src/sharpit/engine/collectors/health.py`
  - `src/sharpit/engine/collectors/threads.py`
  - `src/sharpit/engine/tools.py` (and `src/sharpit/engine/tool_stubs/threads.py` if split by `F`)
  - `tests/engine/test_pools.py`, `tests/engine/test_threads.py`, `tests/engine/test_alembic.py`, `tests/engine/test_health.py`, `tests/engine/test_tools.py`, `tests/fastapi/test_pools_api.py`, `tests/fastapi/test_sqla_absent.py`, `tests/safety/test_d3_safety.py` (new), `tests/masking/test_d3_masking.py` (new)
  - `tests/fixtures/bootui/2.2.0/{database-connection-pools,alembic,health,threads}/nullable.json` (O2: panel lanes own `nullable.json`)
  - `.superpowers/sdd/0.4.0/lanes/D3/{handoff.md,findings.md,field-map.md,checklist.md,docs.md}` (O3: any user-facing text goes in `docs.md`)
- **Files this lane MUST NOT touch (spec §10.3, conventions C2/C5, ownership rules O1–O4):**
  - `src/sharpit/engine/sqla.py` (O1: owned by `A-postgresql`; `F` creates `add_connection_listener`).
  - `tests/fixtures/bootui/2.2.0/<sharpit-id>/captured.json` (or `<name>.captured.json`), `tests/fixtures/bootui/2.2.0/meta.json` (O2: owned by `G0a`), and `tests/fixtures/bootui/2.2.0/<sharpit-id>/provisional.json` (O2: written by a different worker than the lane).
  - `README.md`, `skills/sharpit/SKILL.md`, `examples/fastapi_sqla/`, `tests/test_example_app.py` (O3: write user-facing docs only to `.superpowers/sdd/0.4.0/lanes/D3/docs.md`).
  - `src/sharpit/engine/panels04/*`, `ui/src/lib/panels04/*`, `src/sharpit/engine/panels.py` (`PANELS`), and `ui/src/lib/nav.ts` (O4).
  - `scripts/dev/lane_gate.py`, `tests/complexity_baseline.json` (unless every touched value strictly decreases or an entry is removed), `sonar-baseline.txt`, `tests/engine/test_import_boundary.py` rules, overhead budget constants, `uv.lock`, `pyproject.toml`, `guard.py` (`D1`), `capture/*` (`D2`), `vulns/*`/`mcp.py`/`restapi/*` (`D4`), or any other lane's collector.
  - `tests/test_safety_matrix.py` and `tests/test_masking_corpus.py` (C5: add D3 rows only in `tests/safety/test_d3_safety.py` and `tests/masking/test_d3_masking.py`).
  - `.superpowers/sdd/0.4.0/lanes/*/review.md` and `.superpowers/sdd/0.4.0/lanes/*/gate/*` or `live-verify.md` (C2: written only by the coordinator/reviewer in the integration worktree; `lane_gate.py` refuses lane diffs touching them).

## Definition of Done Coverage (Spec §6.1 — C8 Order)

| # | Spec §6.1 Item (in spec order) | Satisfying Task |
|---|---|---|
| 1 | **Golden parity:** `tests/golden.py::assert_parity` against `tests/fixtures/bootui/2.2.0/<sharpit-id>/captured.json` (or `<name>.captured.json`, else `provisional.json` per O2) + `nullable.json` (owned by D3 per O2), and `field-map.md` | Task 1 (Step 3), Task 2 (Step 1) |
| 2 | **Ported tests:** each ported behaviour test cites `# ported: <BootUI class>.<method>` | Task 1 (Step 1), Task 2 (Step 1) |
| 3 | **Safety & masking:** `no_side_effects` on every GET; panel in `PANELS` with `actionCapable` and `SHARPIT_PANELS_<ID>_ENABLED/_READ_ONLY`; guard chain unchanged; `tests/safety/test_d3_safety.py` & `tests/masking/test_d3_masking.py` | Task 1 (Step 1), Task 2 (Step 1) |
| 4 | **Gatekeeper / import boundary:** SQLAlchemy accessed solely via `src/sharpit/engine/sqla.py` (`sqla.sqlalchemy_module() is not None`, read-only per O1); `tests/engine/test_import_boundary.py` green | Task 1 (Steps 1, 3), Task 2 (Step 4) |
| 5 | **Overhead budget:** `N/A — no capture middleware or SQL listener hot path modified; existing overhead budget tests pass` | Task 2 (Step 4) |
| 6 | **MCP read-only:** MCP exposes read tools only (`get_threads` with `INVENTORY_DEFAULT_LIMIT = 25`, `get_database_connection_pools`, `get_alembic_migrations`, `get_health`); no write tools | Task 2 (Steps 1–3) |
| 7 | **Svelte 5 view:** `N/A — 2.2.0 DTO/MCP drift lane on existing panels` | N/A |
| 8 | **Four gates + lowest-direct + no-SQLAlchemy:** `ruff check`, `ruff format --check`, `pyright`, `pytest` green in lane worktree; coordinator records `gate/*.log` in integration worktree | Task 2 (Step 4) |
| 9 | **Live check:** coordinator records `live-verify.md` in integration worktree against `examples/fastapi_sqla` | Task 2 (Step 4) |
| 10 | **Handoff:** `.superpowers/sdd/0.4.0/lanes/D3/handoff.md` current (§10.3) | Task 2 (Step 4) |

## Review Focus

1. **`hikariPresent` → `poolLibraryPresent` & `implementation` field (`src/sharpit/engine/collectors/pools.py:38-83`)**: BootUI 2.2.0 replaced `hikariPresent` with `poolLibraryPresent: bool` on `DatabaseConnectionPoolsReport` and added `implementation: str | None` (`"SQLAlchemy"`) to `DatabaseConnectionPoolDto` so HikariCP and Agroal/SQLAlchemy share one schema. Keep `def pools_report(ctx: SharpitContext) -> dict[str, Any]:` (`pools.py:74`, called by `src/sharpit/fastapi/adapter.py:431` and `src/sharpit/engine/tools.py:477`) and `def _pool_dto(ctx: SharpitContext, name: str, engine: Any) -> dict[str, Any]:` (`pools.py:38`). Pinned by `test_pools_report_emits_pool_library_present_and_implementation` in **Task 1**.
2. **Honest `null` for `readOnly` and non-AUTOCOMMIT `autoCommit` (`src/sharpit/engine/collectors/pools.py:43-66`)**: SQLAlchemy `Engine`/`Pool` does not expose a pool-level `readOnly` boolean or a boolean `autoCommit` unless `isolation == "AUTOCOMMIT"` (where `isolation = engine.get_execution_options().get("isolation_level") or getattr(engine.dialect, "_on_connect_isolation_level", None)` at `pools.py:43-45`). Emitting `False` fabricated state in 0.3.0; 0.4.0 emits `readOnly: None` and `autoCommit: True if isolation == "AUTOCOMMIT" else None`, documented in `tests/fixtures/bootui/2.2.0/database-connection-pools/nullable.json`. Pinned by `test_pool_dto_emits_null_read_only_and_honest_auto_commit` in **Task 1**.
3. **Graceful degradation when `sqlalchemy` is absent (`src/sharpit/engine/collectors/pools.py:18, 71, 77`; `src/sharpit/engine/sqla.py:41`)**: When `sqla.sqlalchemy_module() is not None` is `False` (the `no-sqlalchemy` CI gate), `pools_report(ctx)` must still return `"poolLibraryPresent": False` and all top-level keys without importing `sqlalchemy`. Pinned by `test_pools_report_without_sqlalchemy_emits_pool_library_present_false` in **Task 1**.
4. **MCP `get_threads` default limit 25 vs HTTP/CLI (`src/sharpit/engine/tools.py:479-487`)**: When `limit` is omitted on MCP `get_threads({})`, `INVENTORY_DEFAULT_LIMIT = 25` caps `threads` to 25 and updates `page.returned`, whereas `GET /sharpit/api/threads` returns the full dump up to `max_items`. Pinned by `test_mcp_get_threads_applies_default_limit_25_when_omitted` in **Task 2**.

---

### Task 1: `database-connection-pools` 2.2.0 Contract Alignment

**Files:**
- Modify: `src/sharpit/engine/collectors/pools.py:16-83`
- Create/Modify: `tests/fixtures/bootui/2.2.0/database-connection-pools/nullable.json`
- Test: `tests/engine/test_pools.py`, `tests/fastapi/test_pools_api.py`, `tests/fastapi/test_sqla_absent.py`, `tests/safety/test_d3_safety.py` (new), `tests/masking/test_d3_masking.py` (new)

**Interfaces:**
- Produces in `src/sharpit/engine/collectors/pools.py`:
  - `def pools_report(ctx: SharpitContext) -> dict[str, Any]:` emitting `"poolLibraryPresent": sqla.sqlalchemy_module() is not None` (removing `"hikariPresent"`).
  - `def _pool_dto(ctx: SharpitContext, name: str, engine: Any) -> dict[str, Any]:` emitting `"implementation": "SQLAlchemy"`, `"readOnly": None`, and `"autoCommit": True if isolation == "AUTOCOMMIT" else None`.

- [ ] **Step 1: Write failing tests in `tests/engine/test_pools.py`, `tests/fastapi/test_pools_api.py`, `tests/fastapi/test_sqla_absent.py`, `tests/safety/test_d3_safety.py`, and `tests/masking/test_d3_masking.py` (C4: RED is an assertion failure)**
  - `# ported: DatabaseConnectionPoolsServiceTests.reportsPoolLibraryPresentAndImplementation` (`test_pools_report_emits_pool_library_present_and_implementation`: asserts `"poolLibraryPresent" in report`, `"hikariPresent" not in report`, and `pool["implementation"] == "SQLAlchemy"`).
  - `test_pool_dto_emits_null_read_only_and_honest_auto_commit`: asserts `pool["readOnly"] is None`, `pool["autoCommit"] is None` by default, and `pool["autoCommit"] is True` when `execution_options={"isolation_level": "AUTOCOMMIT"}`.
  - `test_pools_report_without_sqlalchemy_emits_pool_library_present_false`: monkeypatches `sqla.sqlalchemy_module` to return `None` and verifies `pools_report(ctx)["poolLibraryPresent"] is False`.
  - Safety/masking rows in `tests/safety/test_d3_safety.py` (`no_side_effects` on `pools_report(ctx)`) and `tests/masking/test_d3_masking.py` (DB URL password masking in `jdbcUrl`).
- [ ] **Step 2: Run `uv run pytest -q tests/engine/test_pools.py tests/fastapi/test_pools_api.py tests/fastapi/test_sqla_absent.py tests/safety/test_d3_safety.py tests/masking/test_d3_masking.py` and verify RED**
  - Expected failure: `AssertionError: assert 'poolLibraryPresent' in report` (`'hikariPresent'` was emitted).
- [ ] **Step 3: Update `src/sharpit/engine/collectors/pools.py` and `tests/fixtures/bootui/2.2.0/database-connection-pools/nullable.json`**
  - In `src/sharpit/engine/collectors/pools.py:38-83`, replace `"hikariPresent"` with `"poolLibraryPresent": sqla.sqlalchemy_module() is not None`, add `"implementation": "SQLAlchemy"`, set `"readOnly": None` and `"autoCommit": True if isolation == "AUTOCOMMIT" else None`, and record `idleTimeoutMs`, `maxLifetimeMs`, `validationTimeoutMs`, `keepaliveTimeMs`, `minimumIdle`, `readOnly`, `autoCommit` in `tests/fixtures/bootui/2.2.0/database-connection-pools/nullable.json` (O2 layout).
- [ ] **Step 4: Run `uv run pytest -q tests/engine/test_pools.py tests/fastapi/test_pools_api.py tests/fastapi/test_sqla_absent.py tests/safety/test_d3_safety.py tests/masking/test_d3_masking.py` and commit**
  - Commit: `feat(pools): align database-connection-pools DTO with BootUI 2.2.0`.

---

### Task 2: `threads` MCP Default Limit 25 and `alembic`/`health` 2.2.0 Golden Conformance

**Files:**
- Modify: `src/sharpit/engine/tools.py:479-487` (and `src/sharpit/engine/tool_stubs/threads.py` if split by `F`)
- Test: `tests/engine/test_threads.py`, `tests/engine/test_alembic.py`, `tests/engine/test_health.py`, `tests/engine/test_tools.py`

**Interfaces:**
- Consumes: `tests/golden.py::assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None` from `F` (reads `captured.json` when present, else `provisional.json` per O2).
- Produces in `src/sharpit/engine/tools.py`: `get_threads` MCP handler applies `INVENTORY_DEFAULT_LIMIT = 25` when `args.get("limit")` is `None`.

- [ ] **Step 1: Write failing tests in `tests/engine/test_tools.py`, `tests/engine/test_threads.py`, `tests/engine/test_alembic.py`, and `tests/engine/test_health.py`**
  - `# ported: McpAgentViewsTests.threadsDefaultLimit` (`test_mcp_get_threads_applies_default_limit_25_when_omitted`: creates >25 synthetic thread dicts or mocks `threads_report` and asserts MCP `get_threads({})` requests `limit=25` while explicit `get_threads({"limit": 10})` requests `10`).
  - `test_d3_panels_2_2_0_golden_conformance`: calls `assert_parity` from `tests/golden.py` for `alembic`, `database-connection-pools`, `health`, and `threads` (against `captured.json` or `provisional.json` + `nullable.json` per O2) under `no_side_effects`.
- [ ] **Step 2: Run `uv run pytest -q tests/engine/test_tools.py tests/engine/test_threads.py tests/engine/test_alembic.py tests/engine/test_health.py -k "threads or d3"` and verify RED**
- [ ] **Step 3: Apply `INVENTORY_DEFAULT_LIMIT = 25` in `tools.py` for MCP `get_threads` and verify `alembic`/`health` DTOs**
- [ ] **Step 4: Run verification gates in the lane worktree (`ruff check`, `ruff format --check`, `pyright`, `pytest`), update implementer evidence in `.superpowers/sdd/0.4.0/lanes/D3/`, and commit**
  - Commit: `feat(threads): apply 2.2.0 MCP default limit 25 and verify D3 golden conformance`.

---

## Lane Evidence Checklist (`lane_gate.py` — Spec §10.3 & C2)

**Written by the implementer in the lane worktree (`.superpowers/sdd/0.4.0/lanes/D3/`):**
- [ ] `field-map.md` — Every BootUI 2.2.0 key for `alembic`, `database-connection-pools`, `health`, and `threads` mapped to Python source or `tests/fixtures/bootui/2.2.0/<sharpit-id>/nullable.json`.
- [ ] `findings.md` — `finding → test → red` table with all rows `fixed` or `parked`.
- [ ] `checklist.md` — Spec §6.1's 10 items in spec §6.1's exact order (1 golden parity … 10 handoff), each with an evidence path or `N/A` + reason.
- [ ] `handoff.md` — Last green command, next step (`ready-for-review`), open findings (`none`).

**Written by the coordinator/reviewer in the integration worktree ONLY (never touched by the lane's diff; `lane_gate.py` refuses it):**
- [ ] `review.md` — Fresh reviewer subagent (`reviewer_id != implementer_id`) + `/code-review high` naming head SHA, ending with `VERDICT: APPROVE`.
- [ ] `gate/{ruff-check,ruff-format,pyright,pytest,lowest-direct,no-sqlalchemy}.log` and `live-verify.md`.
