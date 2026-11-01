# Lane D3: 2.2.0 DB & Runtime Panels Drift (`alembic`, `database-connection-pools`, `health`, `threads`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- **Lane ID:** `D3`
- **Goal:** Align `database-connection-pools` (`poolLibraryPresent`, `implementation`, nullable `readOnly`/`autoCommit`), `threads` (`McpAgentViews.INVENTORY_DEFAULT_LIMIT = 25`), `alembic`, and `health` with the BootUI 2.2.0 contract and golden fixtures.
- **Spec sections:** §9 D3 (best effort), §6.1 (definition of done), §10.2 (Order 5), §10.3 (lane gate); contract `docs/reference/BOOTUI-CONTRACT-0.4-DRIFT.md` §§15–18.
- **Worker profile:** **S**, **mechanical** (localized DTO key renames, nullable field alignment, and MCP default limit).
- **Dependencies:** Foundation commit **F** and **D1** must be merged first.
- **Files this lane MAY touch:**
  - `src/sharpit/engine/collectors/pools.py`
  - `src/sharpit/engine/collectors/alembic.py`
  - `src/sharpit/engine/collectors/health.py`
  - `src/sharpit/engine/collectors/threads.py`
  - `src/sharpit/engine/tools.py` (or F's split runtime/DB MCP module)
  - `tests/engine/test_pools.py`, `tests/engine/test_threads.py`, `tests/engine/test_alembic.py`, `tests/engine/test_health.py`, `tests/engine/test_tools.py`, `tests/fastapi/test_pools_api.py`, `tests/test_conformance.py`
  - `tests/fixtures/bootui/2.2.0/database-connection-pools.nullable.json`
  - `.superpowers/sdd/0.4.0/lanes/D3/*`
- **Files this lane MUST NOT touch (spec §10.3 protected files & other lanes):**
  - `scripts/dev/lane_gate.py`, `tests/complexity_baseline.json` (except lowering), `sonar-baseline.txt`, `tests/engine/test_import_boundary.py` rules, overhead budget constants, `uv.lock`, `pyproject.toml`, `guard.py` (D1), `capture/*` (D2), `vulns/*`/`mcp.py`/`restapi/*` (D4), or any new 0.4.0 panel (`P1`–`P10`, `G1`–`G2`).

## Definition of Done Coverage (Spec §6.1)

| §6.1 Item | Satisfying Task | §6.1 Item | Satisfying Task |
|---|---|---|---|
| 1. Golden parity, `nullable.json`, `field-map.md` | Task 1 (Step 3), Task 2 (Step 3) | 6. Ported `# ported:` tests | Task 1 (Step 1), Task 2 (Step 1) |
| 2. Guard chain on all 4 panel routes | Task 2 (Step 4) | 7. Optional-dep (`no-sqlalchemy`) & lowest-direct gates | Task 1 (Step 1), Task 2 (Step 4) |
| 3. Masking (`JDBC/DB URL` credentials & properties) | Task 1 (Step 1) | 8. Overhead budgets untouched | Task 2 (Step 4) |
| 4. `no_side_effects` on all GET/MCP calls | Task 1 (Step 1), Task 2 (Step 1) | 9. Quality gates (`ruff`, `pyright`, `pytest`) | Task 2 (Step 4) |
| 5. MCP & CLI parity (`get_threads` default limit 25) | Task 2 (Step 3) | 10. Live verification (`live-verify.log`) | Task 2 (Step 4) |

## Review Focus

1. **`hikariPresent` → `poolLibraryPresent` & `implementation` field (`pools.py:38-78`)**: BootUI 2.2.0 replaced `hikariPresent` with `poolLibraryPresent: bool` on `DatabaseConnectionPoolsReport` and added `implementation: str | None` (`"SQLAlchemy"`) to `DatabaseConnectionPoolDto` so HikariCP and Agroal/SQLAlchemy share one schema. Pinned by `test_pools_report_emits_pool_library_present_and_implementation` in **Task 1**.
2. **Honest `null` for `readOnly` and non-AUTOCOMMIT `autoCommit` (`pools.py:66-76`)**: SQLAlchemy `Engine`/`Pool` does not expose a pool-level `readOnly` boolean or a boolean `autoCommit` unless `isolation_level == "AUTOCOMMIT"`. Emitting `False` fabricated state in 0.3.0; 0.4.0 emits `readOnly: None` and `autoCommit: True if isolation == "AUTOCOMMIT" else None`, documented in `database-connection-pools.nullable.json`. Pinned by `test_pool_dto_emits_null_read_only_and_honest_auto_commit` in **Task 1**.
3. **Graceful degradation when `sqlalchemy` is absent (`pools.py:21-26`)**: When `sqla.is_available()` is `False` (the `no-sqlalchemy` CI gate), `pools_report` must still return `"poolLibraryPresent": False` and all top-level keys without importing `sqlalchemy`. Pinned by `test_pools_report_without_sqlalchemy_emits_pool_library_present_false` in **Task 1**.
4. **MCP `get_threads` default limit 25 vs HTTP/CLI (`tools.py:479-487`)**: When `limit` is omitted on MCP `get_threads({})`, `McpAgentViews.INVENTORY_DEFAULT_LIMIT = 25` caps `threads` to 25 and updates `page.returned`, whereas `GET /sharpit/api/threads` returns the full dump up to `max_items`. Pinned by `test_mcp_get_threads_applies_default_limit_25_when_omitted` in **Task 2**.

---

### Task 1: `database-connection-pools` 2.2.0 Contract Alignment

**Files:**
- Modify: `src/sharpit/engine/collectors/pools.py:16-83`
- Create/Modify: `tests/fixtures/bootui/2.2.0/database-connection-pools.nullable.json`
- Test: `tests/engine/test_pools.py`, `tests/fastapi/test_pools_api.py`

**Interfaces:**
- Produces in `src/sharpit/engine/collectors/pools.py`:
  - `pools_report(engines: list[Any], masker: Masker, *, query: str | None = None, offset: int = 0, limit: int | None = None, max_items: int = 200) -> dict[str, Any]` emitting `"poolLibraryPresent": available` (removing `"hikariPresent"`).
  - `_pool_dto(idx: int, engine: Any, masker: Masker) -> dict[str, Any]` emitting `"implementation": "SQLAlchemy"`, `"readOnly": None`, and `"autoCommit": True if isolation == "AUTOCOMMIT" else None`.

- [ ] **Step 1: Write failing tests in `tests/engine/test_pools.py` and `tests/fastapi/test_pools_api.py`**
  - `# ported: DatabaseConnectionPoolsServiceTests.reportsPoolLibraryPresentAndImplementation` (`test_pools_report_emits_pool_library_present_and_implementation`: asserts `"poolLibraryPresent" in report`, `"hikariPresent" not in report`, and `pool["implementation"] == "SQLAlchemy"`).
  - `test_pool_dto_emits_null_read_only_and_honest_auto_commit`: asserts `pool["readOnly"] is None`, `pool["autoCommit"] is None` by default, and `pool["autoCommit"] is True` when `execution_options={"isolation_level": "AUTOCOMMIT"}`.
  - `test_pools_report_without_sqlalchemy_emits_pool_library_present_false`: monkeypatches `sqla.is_available` to `False` and verifies `"poolLibraryPresent": False`.
- [ ] **Step 2: Run `uv run pytest -q tests/engine/test_pools.py tests/fastapi/test_pools_api.py` and verify RED**
  - Expected failure: `AssertionError: assert 'poolLibraryPresent' in report` (`'hikariPresent'` was emitted).
- [ ] **Step 3: Update `src/sharpit/engine/collectors/pools.py` and `database-connection-pools.nullable.json`**
  - Replace `"hikariPresent"` with `"poolLibraryPresent"`, add `"implementation": "SQLAlchemy"`, set `"readOnly": None` and `"autoCommit": True if isolation == "AUTOCOMMIT" else None`, and record `connectionTimeoutMillis`, `idleTimeoutMillis`, `maxLifetimeMillis`, `validationTimeoutMillis`, `keepaliveTimeMillis`, `leakDetectionThresholdMillis`, `minimumIdle`, `readOnly`, `autoCommit`, `catalog`, `schema` in `database-connection-pools.nullable.json`.
- [ ] **Step 4: Run `uv run pytest -q tests/engine/test_pools.py tests/fastapi/test_pools_api.py` and commit**
  - Commit: `feat(pools): align database-connection-pools DTO with BootUI 2.2.0`.

---

### Task 2: `threads` MCP Default Limit 25 and `alembic`/`health` 2.2.0 Golden Conformance

**Files:**
- Modify: `src/sharpit/engine/tools.py:479-487` (or F's split runtime MCP module)
- Test: `tests/engine/test_threads.py`, `tests/engine/test_alembic.py`, `tests/engine/test_health.py`, `tests/engine/test_tools.py`, `tests/test_conformance.py`

**Interfaces:**
- Produces in `src/sharpit/engine/tools.py`: `get_threads` MCP handler applies `INVENTORY_DEFAULT_LIMIT = 25` when `args.get("limit")` is `None`.

- [ ] **Step 1: Write failing tests in `tests/engine/test_tools.py` and `tests/test_conformance.py`**
  - `# ported: McpAgentViewsTests.threadsDefaultLimit` (`test_mcp_get_threads_applies_default_limit_25_when_omitted`: creates >25 synthetic thread dicts or mocks `threads_report` and asserts MCP `get_threads({})` requests `limit=25` while explicit `get_threads({"limit": 10})` requests `10`).
  - `test_d3_panels_2_2_0_golden_conformance`: verifies `alembic`, `database-connection-pools`, `health`, and `threads` match `tests/fixtures/bootui/2.2.0/` keys under `no_side_effects`.
- [ ] **Step 2: Run `uv run pytest -q tests/engine/test_tools.py tests/test_conformance.py -k "threads or d3"` and verify RED**
- [ ] **Step 3: Apply `INVENTORY_DEFAULT_LIMIT = 25` in `tools.py` for MCP `get_threads` and verify `alembic`/`health` DTOs**
- [ ] **Step 4: Run full verification gates (`ruff`, `pyright`, `pytest`, `lowest-direct.log`, `no-sqlalchemy.log`, `live-verify.log`) and commit**
  - Commit: `feat(threads): apply 2.2.0 MCP default limit 25 and verify D3 golden conformance`.

---

## Lane Evidence Checklist (`lane_gate.py` — Spec §10.3)

`.superpowers/sdd/0.4.0/lanes/D3/` MUST contain:
- [ ] `field-map.md` — Every BootUI 2.2.0 key for `alembic`, `database-connection-pools`, `health`, and `threads` mapped to Python source or `nullable.json`.
- [ ] `findings.md` — `finding → test → red` table with all rows `fixed` or `parked`.
- [ ] `checklist.md` — Spec §6.1 items 1–10 with `lowest-direct.log`, `no-sqlalchemy.log`, and `live-verify.log` naming the head SHA.
- [ ] `handoff.md` — Last green command, next step, open findings.
- [ ] `review.md` — Fresh reviewer subagent (`reviewer_id != implementer_id`) + `/code-review high` naming head SHA, ending with `VERDICT: APPROVE`.
