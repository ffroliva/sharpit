# Lanes G0a & G0b: BootUI 2.2.0 Golden Capture (§G0a) and `tiny-ledger-py` Increments 1–2 (§G0b)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> This file contains two independent, non-blocking parallel lanes (`PLAN.md` lines 72–73):
> - **§G0a (`G0a`):** runs in a `sharpit` worktree (`C:\development\github\sharpit-wt\0.4.0-G0a`), depends on `F`, and populates **only** `tests/fixtures/bootui/2.2.0/<sharpit-id>/captured.json` (or `<name>.captured.json` for a multi-endpoint panel, plus `tests/fixtures/bootui/2.2.0/meta.json` and raw captures in `replica/evidence/2.2.0/<sharpit-id>/`) per ownership rule **O2** (amends C3; `F` owns `tests/golden.py` and `tests/fixtures/bootui/2.2.0/ids.json`, and panel lanes own `nullable.json`).
> - **§G0b (`G0b`):** runs in its own repository (`C:\development\github\tiny-ledger-py`) on a **different worker account from `G0a`**, depends on `—`, and its evidence lives in `tiny-ledger-py` (reported to the coordinator, not gated by `sharpit`'s `lane_gate.py`).

---

## §G0a — BootUI 2.2.0 Golden Capture (`G0a`)

- **Lane ID:** `G0a`
- **Evidence folder:** `.superpowers/sdd/0.4.0/lanes/G0a/`
- **Class:** parallel, never blocking (`PLAN.md` line 72)
- **Depends on:** `F` (`F` creates `tests/golden.py::assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None` and `tests/fixtures/bootui/2.2.0/ids.json`; `G0a` populates `captured.json` / `<name>.captured.json` fixtures under the O2 directory layout only).
- **Default worker:** `codex (medium)`
- **Goal:** Capture and sanitise live BootUI 2.2.0 JSON golden fixtures into `tests/fixtures/bootui/2.2.0/<sharpit-id>/captured.json` (and `<name>.captured.json` for multi-endpoint panels, plus `tests/fixtures/bootui/2.2.0/meta.json`) from `tiny-ledger-bootui-ref`, with raw captures in `replica/evidence/2.2.0/<sharpit-id>/` (not mined).
- **Spec sections:** §2 G0, §6.1 (definition of done), §6.1.1 (golden fixture rules, `nullable.json`, provisional fallback), §6.2 (panel ID mapping), §10.1 (multi-agent port leasing via `agentctl.py`), §10.2 (Order 1, parallel with all waves), §10.3 (lane gate), §12.11 (live vs provisional golden rule); `C:\development\github\tiny-ledger-bootui-ref\README.md` §§"Access URLs", "Run the backend"; `C:\development\github\tiny-ledger-bootui-ref\ledger-cli\NOTES.md` §Auth; `docs/reference/BOOTUI-CONTRACT-MVP.md` §10.
- **Foundation interfaces consumed (`F-foundation.md` §"Foundation consumer interface table"):**
  - `tests.golden.assert_parity` (`def assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None` + `tests/fixtures/bootui/2.2.0/ids.json`, owned by `F`: reads `captured.json` or `<name>.captured.json` when present, else `provisional.json` and marks the result unverified per O2)
  - `scripts/dev/lane_gate.py` (`python scripts/dev/lane_gate.py G0a`)
- **Files `G0a` MAY touch:**
  - `scripts/sanitize_golden.py`
  - `replica/evidence/2.2.0/<sharpit-id>/captured.json` (and `<name>.captured.json` for multi-endpoint panels; `replica/evidence/2.2.0/` is not mined)
  - `tests/fixtures/bootui/2.2.0/<sharpit-id>/captured.json` (and `<name>.captured.json` for multi-endpoint panels) and `tests/fixtures/bootui/2.2.0/meta.json` (O2 layout — `G0a` writes **only** `captured.json` / `<name>.captured.json` + `meta.json`; no flat `<panel>.json` files and no `nullable.json` files)
  - `tests/test_sanitize_golden.py`, `tests/test_conformance.py`
  - `.superpowers/sdd/0.4.0/lanes/G0a/{handoff.md,findings.md,field-map.md,checklist.md,docs.md}` (O3: any user-facing text goes in `docs.md`)
- **Files `G0a` MUST NOT touch (spec §10.3, conventions C2/C5, ownership rules O1–O4):**
  - `tests/fixtures/bootui/2.2.0/<sharpit-id>/nullable.json` (O2: owned by panel lanes) and `tests/fixtures/bootui/2.2.0/<sharpit-id>/provisional.json` (O2: written by a different worker than the panel lane when live capture is not available).
  - `src/sharpit/**` (including `src/sharpit/engine/sqla.py` per O1 and `src/sharpit/engine/panels04/*` per O4), `ui/**` (O4), `tests/golden.py`, `tests/fixtures/bootui/2.2.0/ids.json` (owned by `F`), `scripts/dev/lane_gate.py`, `tests/complexity_baseline.json`, `sonar-baseline.txt`, `tests/engine/test_import_boundary.py`, overhead budget constants, `uv.lock`, `pyproject.toml`.
  - `README.md`, `skills/sharpit/SKILL.md`, `examples/fastapi_sqla/`, `tests/test_example_app.py` (O3).
  - `tests/test_safety_matrix.py` and `tests/test_masking_corpus.py` (C5).
  - `.superpowers/sdd/0.4.0/lanes/*/review.md` and `.superpowers/sdd/0.4.0/lanes/*/gate/*` or `live-verify.md` (C2: written only by the coordinator/reviewer in the integration worktree; `lane_gate.py` refuses lane diffs touching them).
  - `C:\development\github\tiny-ledger-bootui-ref` tracked files (treat reference repo as read-only runtime target).

### Definition of Done Coverage for `G0a` (Spec §6.1 — C8 Order)

| # | Spec §6.1 Item (in spec order) | Satisfying Task |
|---|---|---|
| 1 | **Golden parity:** `tests/fixtures/bootui/2.2.0/<sharpit-id>/captured.json` (and `<name>.captured.json` for multi-endpoint panels) + `meta.json` populated (O2; panel lanes own `nullable.json`) and verified via `tests/golden.py::assert_parity`, and `field-map.md` | Task G0a.1, Task G0a.2 (Steps 1–4) |
| 2 | **Ported tests:** `N/A — golden capture and sanitiser lane; panel lanes own ported behaviour tests` | N/A |
| 3 | **Safety & masking:** `scripts/sanitize_golden.py::find_secrets(node) == []` across every captured fixture | Task G0a.2 (Steps 1–3) |
| 4 | **Gatekeeper / import boundary:** `tests/engine/test_import_boundary.py` green (`src/sharpit/` untouched) | Task G0a.2 (Step 4) |
| 5 | **Overhead budget:** `N/A — fixture and script lane only; runtime hot paths untouched` | N/A |
| 6 | **MCP read-only:** `N/A — no MCP or CLI tools modified` | N/A |
| 7 | **Svelte 5 view:** `N/A — no UI view modified` | N/A |
| 8 | **Four gates + lowest-direct + no-SQLAlchemy:** `ruff check`, `ruff format --check`, `pyright`, `pytest` green in lane worktree; coordinator records `gate/*.log` in integration worktree | Task G0a.2 (Step 4) |
| 9 | **Live check:** live capture against `tiny-ledger-bootui-ref` on leased ports (`8080`, `5432`, `6379`, `9092`, `443`); coordinator records `live-verify.md` in integration worktree | Task G0a.1 (Steps 1–3) |
| 10 | **Handoff:** `.superpowers/sdd/0.4.0/lanes/G0a/handoff.md` current (§10.3) | Task G0a.2 (Step 4) |

### Review Focus (`G0a`)

1. **TLS & Auth discipline against `tiny-ledger-bootui-ref` (`README.md:66-71`, `ledger-cli/NOTES.md:99-106`, `BOOTUI-CONTRACT-MVP.md` §10)**:
   - Business API calls to `https://app.localhost/api/v1/*` require a Keycloak Bearer JWT obtained via password grant (`POST https://auth.localhost/realms/tiny-ledger/protocol/openid-connect/token`, `client_id=ledger-test`, `grant_type=password`, `username=alice`, `password=alice`) verified against `C:\development\github\tiny-ledger-bootui-ref\docker\tls\ca.crt` (never `verify=False` or `curl -k`).
   - BootUI console API calls (`/bootui/api/*`) use BootUI's own guard on `http://127.0.0.1:8080/bootui/api/*` (loopback `127.0.0.1`, `Host: 127.0.0.1:8080`, plus `Authorization: Bearer <bootui.authentication.token>` or `POST /bootui/api/auth/session` `BOOTUI_SESSION` cookie when token auth is configured). Mixing the two tokens causes 401/403. Pinned by `test_golden_capture_manifest_has_all_2_2_0_panels_and_no_error_envelopes` in **Task G0a.2**.
2. **Secret and volatile-field sanitisation in `scripts/sanitize_golden.py:19-83`**:
   - BootUI 2.2.0 adds `instanceId`, `runId`, `startedAt`, `checkedAt`, `oldestTimestamp`, `newestTimestamp`, and `durationMicros`. `sanitise(node: Any) -> Any` (`scripts/sanitize_golden.py:42`) and `find_secrets(node: Any, where: str = "$", key: str = "") -> list[str]` (`scripts/sanitize_golden.py:63`) must scrub secret patterns (`find_secrets(data) == []`), normalize volatile IDs/timestamps, and write `"bootuiVersion": "2.2.0"` in `tests/fixtures/bootui/2.2.0/meta.json`. Pinned by `test_sanitize_golden_scrubs_2_2_0_volatile_keys_and_secrets` in **Task G0a.2**.
3. **O2 Fixture Ownership & Live vs Provisional Golden separation (spec §6.1.1, §12.11, and O2 amending C3)**:
   - `G0a` writes **only** `tests/fixtures/bootui/2.2.0/<sharpit-id>/captured.json` (or `<name>.captured.json` for a multi-endpoint panel) and `tests/fixtures/bootui/2.2.0/meta.json`, with raw captures in `replica/evidence/2.2.0/<sharpit-id>/` (which is not mined), using the BootUI→sharpit mapping in `tests/fixtures/bootui/2.2.0/ids.json` owned by `F`. Panel lanes own `tests/fixtures/bootui/2.2.0/<sharpit-id>/nullable.json` — `G0a` never writes `nullable.json` so `G0a` and panel lanes have zero file collisions.
   - `tests/golden.py::assert_parity(sharpit_id, name, payload)` reads `captured.json` (or `<name>.captured.json` for a multi-endpoint panel) when present, else `provisional.json` and marks the result unverified. Any panel whose live capture cannot be triggered against `tiny-ledger-bootui-ref` is listed in `tests/fixtures/bootui/2.2.0/meta.json` under `"provisional": ["<sharpit-id>"]`; its `provisional.json` is built from BootUI 2.2.0 record definitions in `C:\development\github\boot-ui-ref\bootui-engine\src\main\java\io\github\jdubois\bootui\core\dto\` by a different worker than the panel lane. Pinned by `test_conformance_2_2_0_goldens_and_ids_mapping` in **Task G0a.2**.

### Task G0a.1: Lease Reference Stack, Drive Seed Traffic via Keycloak JWT, and Capture Raw BootUI 2.2.0 Evidence

**Files:**
- Create: `replica/evidence/2.2.0/<sharpit-id>/captured.json` (and `<name>.captured.json` for multi-endpoint panels such as `http-exchanges/routes.captured.json`, `exceptions/caught.captured.json`, `activity/journal.captured.json`, `activity/resources.captured.json`, for all BootUI 2.2.0 panels mapped via `ids.json` + `overview`, `panels`, `dismissed-rules`, `dismissed-findings`)

**Interfaces:**
- Consumes: `C:\development\github\tiny-ledger-bootui-ref\docker\docker-compose.yml`, `docker/tls/ca.crt`, `http://127.0.0.1:8080/bootui/api/*`, `tests/fixtures/bootui/2.2.0/ids.json` (from `F`).
- Produces: Raw JSON captures in `replica/evidence/2.2.0/<sharpit-id>/captured.json` (and `<name>.captured.json`; not mined).

- [ ] **Step 1: Join `agentctl.py` and lease reference stack ports (`5432`, `6379`, `9092`, `443`, `8080`)**
  - Run `python ~/.agents/skills/multi-agent-dev/scripts/agentctl.py join --title "G0a" --role "G0a 2.2.0 goldens"` and lease `--global postgres-5432`, `--global redis-6379`, `--global kafka-9092`, `--global traefik-443`, and `app-port` `8080`.
  - Ensure `tiny-ledger-bootui-ref` Docker stack (`docker compose -f docker/docker-compose.yml up -d`) and `./gradlew bootRun` (on branch `chore/bootui-2.2.0-goldens`) are healthy (`GET http://127.0.0.1:8080/actuator/health` → `200 UP`).
- [ ] **Step 2: Obtain Keycloak token using `docker/tls/ca.crt` and seed ledger activity**
  - Using Python `httpx.Client(verify="C:/development/github/tiny-ledger-bootui-ref/docker/tls/ca.crt")`, POST to `https://auth.localhost/realms/tiny-ledger/protocol/openid-connect/token` with `data={"client_id": "ledger-test", "grant_type": "password", "username": "alice", "password": "alice"}`.
  - With `Authorization: Bearer <access_token>`, drive `POST /api/v1/accounts`, `PUT /api/v1/accounts/{uid}/deposits/{depUid}`, `PUT /api/v1/accounts/{uid}/withdrawals/{wdUid}`, `GET /api/v1/accounts/{uid}/balance?consistency=strong`, `GET /api/v1/accounts/{uid}/transactions`, plus one deliberate 422 overdraft and one 404 account lookup so `http-exchanges`, `sql-trace`, `exceptions`, `sqlalchemy-statistics` (`hibernate-statistics`), `transactions`, `caches`, `messaging`, and `postgresql` have rich runtime state.
- [ ] **Step 3: Authenticate to BootUI `/bootui/api/*` on `127.0.0.1:8080` and capture all 2.2.0 endpoints**
  - Connect to `http://127.0.0.1:8080/bootui/api` with `Host: 127.0.0.1:8080` (and `Authorization: Bearer <token>` or `BOOTUI_SESSION` cookie via `POST /bootui/api/auth/session` if `bootui.authentication.token` is set, per `BOOTUI-CONTRACT-MVP.md` §10).
  - Trigger explicit scan/read actions first (`POST /bootui/api/postgresql/read`, `POST /bootui/api/rest-api/scan`, `POST /bootui/api/vulnerabilities/scan`), then fetch and save every panel's GET JSON into `replica/evidence/2.2.0/<sharpit-id>/captured.json` (plus sub-route fixtures such as `http-exchanges/routes.captured.json`, `exceptions/caught.captured.json`, `activity/journal.captured.json`, `activity/resources.captured.json`).

### Task G0a.2: Update `scripts/sanitize_golden.py` for 2.2.0 and Populate `tests/fixtures/bootui/2.2.0/<sharpit-id>/captured.json`

**Files:**
- Modify: `scripts/sanitize_golden.py:19-109`
- Create: `tests/fixtures/bootui/2.2.0/<sharpit-id>/captured.json` (and `<name>.captured.json` for multi-endpoint panels), `tests/fixtures/bootui/2.2.0/meta.json`
- Modify: `tests/test_sanitize_golden.py`, `tests/test_conformance.py`

**Interfaces:**
- Consumes: `tests/golden.py::assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None` and `tests/fixtures/bootui/2.2.0/ids.json` from `F`.
- Produces in `scripts/sanitize_golden.py`: `sanitise(node: Any) -> Any` (`scripts/sanitize_golden.py:42`) handling 2.2.0 volatile keys (`instanceId`, `runId`, `startedAt`, `checkedAt`, `oldestTimestamp`, `newestTimestamp`) and recursive `<sharpit-id>/captured.json` (and `<name>.captured.json`) output in `main(src: Path, dst: Path) -> None` (`scripts/sanitize_golden.py:83`) without touching `<sharpit-id>/nullable.json` or `provisional.json` (O2).

- [ ] **Step 1: Write failing tests in `tests/test_sanitize_golden.py` and `tests/test_conformance.py` (C4: RED is an assertion failure)**
  - `test_sanitize_golden_scrubs_2_2_0_volatile_keys_and_secrets`: verifies `sanitise` normalizes `instanceId` and `runId` to `"00000000"`, `startedAt`/`checkedAt`/`oldestTimestamp`/`newestTimestamp` to `1700000000000`, and `find_secrets(out) == []`.
  - `test_golden_capture_manifest_has_all_2_2_0_panels_and_no_error_envelopes`: verifies every captured 0.4.0 panel has `tests/fixtures/bootui/2.2.0/<sharpit-id>/captured.json` (or is listed under `"provisional"` in `meta.json`), no flat `<panel>.json` files exist, and no fixture is a guard `{"error": ...}` body.
- [ ] **Step 2: Run `uv run pytest -q tests/test_sanitize_golden.py tests/test_conformance.py` and verify RED**
- [ ] **Step 3: Update `scripts/sanitize_golden.py`, run it on `replica/evidence/2.2.0` → `tests/fixtures/bootui/2.2.0` producing `<sharpit-id>/captured.json` (and `<name>.captured.json`), and write `tests/fixtures/bootui/2.2.0/meta.json` (leaving `nullable.json` to panel lanes per O2)**
- [ ] **Step 4: Run verification gates in the `G0a` worktree (`ruff check`, `ruff format --check`, `pyright`, `pytest`), update implementer evidence in `.superpowers/sdd/0.4.0/lanes/G0a/`, and commit** (`test(goldens): add sanitised BootUI 2.2.0 captured golden fixtures`).

### Lane Evidence Checklist for `G0a` (`lane_gate.py` — Spec §10.3 & C2)

**Written by the implementer in the `G0a` lane worktree (`.superpowers/sdd/0.4.0/lanes/G0a/`):**
- [ ] `field-map.md` — Manifest of all captured `tests/fixtures/bootui/2.2.0/<sharpit-id>/captured.json` (and `<name>.captured.json`) files and any panel listed under `"provisional"` in `meta.json` (spec §6.1.1, §12.11, and O2).
- [ ] `findings.md` — `finding → test → red` table with all rows `fixed` or `parked`.
- [ ] `checklist.md` — Spec §6.1's 10 items in spec §6.1's exact order (1 golden parity … 10 handoff), each with an evidence path or `N/A` + reason.
- [ ] `handoff.md` — Current state of `G0a`, last green command, next step (`ready-for-review`), open findings (`none`).

**Written by the coordinator/reviewer in the integration worktree ONLY (never touched by `G0a`'s diff; `lane_gate.py` refuses it):**
- [ ] `review.md` — Fresh reviewer subagent (`reviewer_id != implementer_id`) + `/code-review high` naming head SHA, ending with `VERDICT: APPROVE`.
- [ ] `gate/{ruff-check,ruff-format,pyright,pytest,lowest-direct,no-sqlalchemy}.log` and `live-verify.md`.

---

## §G0b — `tiny-ledger-py` Increments 1–2 (`G0b`)

- **Lane ID:** `G0b`
- **Repository:** `C:\development\github\tiny-ledger-py` (independent repository, branches `feat/increment-1-ledger` and `feat/increment-2-sharpit`)
- **Class:** parallel, never blocking (`PLAN.md` line 73; spec §12.8)
- **Depends on:** `—` (independent of `sharpit` lanes)
- **Default worker:** `agy (Argon)`, on a **different worker account from `G0a`** (`PLAN.md` line 73)
- **Evidence & gating:** `G0b` runs in `C:\development\github\tiny-ledger-py`; its evidence lives in `C:\development\github\tiny-ledger-py` and is **reported** to the coordinator for the morning report, **not** gated by `sharpit`'s `scripts/dev/lane_gate.py`.
- **Goal:** Build `tiny-ledger-py` Increments 1–2 (Postgres event-sourced ledger + `sharpit.install(app, models=Base, engines=[engine])` Dogfooding App #1) in `C:\development\github\tiny-ledger-py`.
- **Spec sections:** §2 G0, §10.1 (`agentctl.py` port leasing), §12.8 (`tiny-ledger-py` scope & non-blocking rule); `C:\development\github\tiny-ledger-py\docs\design.md` §§1–8.
- **Files `G0b` MAY touch (all in `C:\development\github\tiny-ledger-py`):**
  - `pyproject.toml`, `alembic.ini`, `migrations/env.py`, `migrations/versions/001_*.py`–`006_*.py`, `src/tiny_ledger/**`, `tests/**`
- **Files `G0b` MUST NOT touch:**
  - Any file in `C:\development\github\sharpit*` or `C:\development\github\tiny-ledger-bootui-ref`.

### Review Focus (`G0b`)

1. **Integer-cent money invariants & optimistic locking in `tiny-ledger-py` (`C:\development\github\tiny-ledger-py\docs\design.md` §3)**:
   - `Money` must reject floats and negative/zero movement amounts, enforce scale = 2 (`BigDecimal` parity), and `Account` deposits/withdrawals must be idempotent by `depositUid`/`withdrawalUid` and raise HTTP 409 (`https://tiny-ledger.example.com/problems/optimistic-lock-conflict`) on concurrent version conflict. Pinned by `test_domain_money_and_account_invariants` and `test_optimistic_lock_conflict_returns_409_problem_detail` in **Task G0b.1**.
2. **`sharpit.install(app, models=Base, engines=[engine])` route non-interference (`C:\development\github\tiny-ledger-py\docs\design.md` §6)**:
   - Mounting sharpit at `/sharpit` in `tiny-ledger-py` must not shadow `/api/v1/*` routes or alter RFC 7807 `application/problem+json` error responses, and `GET /sharpit/api/data` + `GET /sharpit/api/postgresql` must discover the 4 ledger tables (`events`, `account_summary`, `account_transactions`, `audit_log`). Pinned by `test_sharpit_mount_discovers_ledger_models_and_preserves_api_v1` in **Task G0b.2**.

### Task G0b.1: `tiny-ledger-py` Increment 1 — Core Ledger, Alembic 001–006, and `/api/v1` Endpoints

**Files (all in `C:\development\github\tiny-ledger-py` on branch `feat/increment-1-ledger`):**
- Create: `pyproject.toml`, `alembic.ini`, `migrations/env.py`, `migrations/versions/001_init_event_store.py`..`006_index_events_global_index.py`
- Create: `src/tiny_ledger/settings.py`, `src/tiny_ledger/domain/{money.py,account.py,events.py,policy.py}`, `src/tiny_ledger/adapters/outbound/postgres/{models.py,repositories.py}`, `src/tiny_ledger/adapters/inbound/rest/{app.py,routes.py,problems.py}`, `src/tiny_ledger/application/ledger_service.py`
- Test: `tests/unit/test_domain.py`, `tests/integration/test_ledger_api.py`

**Interfaces:**
- Produces in `tiny_ledger`:
  - `Money(amount: Decimal)` (2 decimal places, non-negative, rejects `float`); `Account.deposit(uid, amount, description, now)`, `Account.withdraw(uid, amount, description, now)`.
  - SQLAlchemy 2 `Base` models `EventRow` (`events`), `AccountSummaryRow` (`account_summary`), `AccountTransactionRow` (`account_transactions`), `AuditLogRow` (`audit_log`).
  - FastAPI routes: `POST /api/v1/accounts` (201), `GET /api/v1/accounts` (200), `GET /api/v1/accounts/{accountUid}` (200/404), `PUT /api/v1/accounts/{accountUid}/deposits/{depositUid}` (200 idempotent), `PUT /api/v1/accounts/{accountUid}/withdrawals/{withdrawalUid}` (200/422), `GET /api/v1/accounts/{accountUid}/balance` (200), `GET /api/v1/accounts/{accountUid}/transactions` (200 keyset cursor), plus `501` RFC 7807 stub on `/events` and `/audit/entries` (`design.md` §2).

- [ ] **Step 1: Add minimal domain/app stubs, then write failing unit and API tests in `C:\development\github\tiny-ledger-py\tests\` (C4: RED is an assertion failure)**
  - `test_domain_money_and_account_invariants`: pins integer-cent scale, idempotent deposit/withdrawal replay, overdraft rejection (`422`), and closed/frozen account rejection.
  - `test_optimistic_lock_conflict_returns_409_problem_detail`: pins RFC 7807 `application/problem+json` with `type="https://tiny-ledger.example.com/problems/optimistic-lock-conflict"`.
  - `test_standalone_profile_runs_full_account_lifecycle_without_docker`: exercises open → deposit → withdraw → balance → keyset transactions in `TINY_LEDGER_PROFILE=standalone`.
- [ ] **Step 2: Run `uv run pytest -q` in `C:\development\github\tiny-ledger-py` and verify RED**
- [ ] **Step 3: Implement domain, Alembic migrations 001–006, Postgres & standalone repositories, and FastAPI `/api/v1` routes**
- [ ] **Step 4: Lease `postgres-5432` via `agentctl.py`, run `uv run pytest -q` against both `standalone` and Docker Postgres (`localhost:5432`), and commit in `tiny-ledger-py`** (`feat(ledger): implement Increment 1 core ledger, Alembic 001-006, and /api/v1 endpoints`).

### Task G0b.2: `tiny-ledger-py` Increment 2 — Mount `sharpit.install(app)` and Enable `pytest --sharpit` Gate

**Files (all in `C:\development\github\tiny-ledger-py` on branch `feat/increment-2-sharpit`):**
- Modify: `pyproject.toml` (editable/path dependency on `sharpit`), `src/tiny_ledger/adapters/inbound/rest/app.py`
- Create: `tests/integration/test_sharpit_mount.py`

**Interfaces:**
- Produces in `src/tiny_ledger/adapters/inbound/rest/app.py`:
  - `sharpit.install(app, models=Base, engines=[engine])` mounted at `/sharpit` (`api_path="/sharpit/api"`).

- [ ] **Step 1: Write failing integration test `tests/integration/test_sharpit_mount.py` in `tiny-ledger-py`**
  - `test_sharpit_mount_discovers_ledger_models_and_preserves_api_v1`: verifies `/api/v1/accounts` works unchanged, `/sharpit/api/overview` and `/sharpit/api/panels` return 200 on loopback, and `/sharpit/api/http-exchanges` + `/sharpit/api/sql-trace` record the ledger requests.
- [ ] **Step 2: Run `uv run pytest -q tests/integration/test_sharpit_mount.py` and verify RED** (`404` assertion failure on `/sharpit/api/overview`).
- [ ] **Step 3: Wire `sharpit.install(app, models=Base, engines=[engine])` in `create_app()` and configure `pytest --sharpit`**
- [ ] **Step 4: Lease port `8081` via `agentctl.py`, run live verification against `http://127.0.0.1:8081/sharpit/api/*`, record evidence in `C:\development\github\tiny-ledger-py` for the coordinator's morning report, and commit in `tiny-ledger-py`** (`feat(sharpit): mount sharpit console at /sharpit and enable pytest --sharpit gate`).
