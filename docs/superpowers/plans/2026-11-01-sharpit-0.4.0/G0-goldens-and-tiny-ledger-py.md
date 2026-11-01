# Lane G0: BootUI 2.2.0 Golden Capture (G0a) and `tiny-ledger-py` Increments 1–2 (G0b)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- **Lane ID:** `G0` (`G0a` in `sharpit` worktree; `G0b` in `C:\development\github\tiny-ledger-py`)
- **Goal:** Capture and sanitise live BootUI 2.2.0 JSON golden fixtures (plus `ids.json` and per-panel `nullable.json`) from `tiny-ledger-bootui-ref`, and build `tiny-ledger-py` Increments 1–2 (Postgres event-sourced ledger + `sharpit.install(app)` Dogfooding App #1) in its own repository without blocking any sharpit panel lane.
- **Spec sections:** §2 G0, §6.1.1 (golden fixture rules, `ids.json`, `nullable.json`, provisional fallback), §6.2 (panel ID mapping), §10.1 (multi-agent port leasing via `agentctl.py`), §10.2 (Order 1, parallel with all waves), §10.3 (lane gate), §12.8 (`tiny-ledger-py` scope & non-blocking rule), §12.11 (live vs provisional golden rule); `C:\development\github\tiny-ledger-py\docs\design.md` §§1–8; `C:\development\github\tiny-ledger-bootui-ref\README.md` §§"Access URLs", "Run the backend"; `C:\development\github\tiny-ledger-bootui-ref\ledger-cli\NOTES.md` §Auth; `docs/reference/BOOTUI-CONTRACT-MVP.md` §10.
- **Worker profile:** **M**, **mechanical** (`G0a`: live HTTP capture, `sanitize_golden.py`, fixture verification; `G0b`: FastAPI + SQLAlchemy 2 + Alembic port of `tiny-ledger` core ledger + `sharpit.install`).
- **Dependencies:**
  - `G0a` depends on Foundation commit **F** (for `tests/fixtures/bootui/2.2.0/` loader & `ids.json` convention).
  - `G0b` runs in `C:\development\github\tiny-ledger-py` (`feat/increment-1-ledger` and `feat/increment-2-sharpit`) and **never blocks** any sharpit lane (spec §12.8).
- **Files this lane MAY touch:**
  - **In `sharpit` (`G0a`):**
    - `scripts/sanitize_golden.py`
    - `replica/evidence/2.2.0/*.json`
    - `tests/fixtures/bootui/2.2.0/*.json`, `tests/fixtures/bootui/2.2.0/ids.json`, `tests/fixtures/bootui/2.2.0/*.nullable.json`, `tests/fixtures/bootui/2.2.0/meta.json`
    - `tests/test_conformance.py`, `tests/test_sanitize_golden.py`
    - `.superpowers/sdd/0.4.0/lanes/G0/*`
  - **In `C:\development\github\tiny-ledger-py` (`G0b`):**
    - `pyproject.toml`, `alembic.ini`, `migrations/env.py`, `migrations/versions/001_*.py`–`006_*.py`, `src/tiny_ledger/**`, `tests/**`
- **Files this lane MUST NOT touch (spec §10.3 protected files & other lanes):**
  - `src/sharpit/**` (product code in sharpit is owned by F, P1–P10, G1–G2, D1–D4), `scripts/dev/lane_gate.py`, `tests/complexity_baseline.json`, `sonar-baseline.txt`, `tests/engine/test_import_boundary.py`, overhead budget constants, `uv.lock`, `pyproject.toml` in `sharpit`.
  - `C:\development\github\tiny-ledger-bootui-ref` tracked files (treat reference repo as read-only runtime target).

## Definition of Done Coverage (Spec §6.1.1, §12.8, §12.11)

| Requirement | Spec Ref | Satisfying Task |
|---|---|---|
| Lease shared Docker / Java / Python ports via `agentctl.py` (never `docker compose down -v`) | §10.1 | Task 1 (Step 1), Task 3 (Step 1) |
| Authenticate to Keycloak via ROPC (`client_id=ledger-test`, CA `docker/tls/ca.crt`, never `-k`) & seed ledger traffic | §2 G0, `NOTES.md` §Auth | Task 1 (Steps 2–3) |
| Authenticate to BootUI `/bootui/api/*` per `BOOTUI-CONTRACT-MVP.md` §10 (`127.0.0.1:8080` + Bearer/session token) | §2 G0, Contract §10 | Task 1 (Step 3) |
| Sanitise all 2.2.0 panel responses via `scripts/sanitize_golden.py` (`find_secrets(data) == []`) into `tests/fixtures/bootui/2.2.0/` | §6.1.1 | Task 2 (Steps 1–3) |
| Emit `ids.json` (BootUI → sharpit panel IDs) and per-panel `<panel>.nullable.json` + `meta.json` (`provisional` flag) | §6.1.1, §6.2, §12.11 | Task 2 (Steps 3–4) |
| `tiny-ledger-py` Increment 1: Alembic 001–006, domain (`Account`, `Money`, `MovementEvent`, `OverdraftPolicy`), `/api/v1` core routes, `standalone` mode | §12.8, `design.md` §8 | Task 3 (Steps 1–4) |
| `tiny-ledger-py` Increment 2: `sharpit.install(app, models=Base, engines=[engine])` at `/sharpit` + `pytest --sharpit` gate | §12.8, `design.md` §§6, 8 | Task 4 (Steps 1–4) |

## Review Focus

1. **TLS & Auth discipline against `tiny-ledger-bootui-ref` (`README.md:66-71`, `ledger-cli/NOTES.md:99-106`, `BOOTUI-CONTRACT-MVP.md` §10)**:
   - Business API calls to `https://app.localhost/api/v1/*` require a Keycloak Bearer JWT obtained via password grant (`POST https://auth.localhost/realms/tiny-ledger/protocol/openid-connect/token`, `client_id=ledger-test`, `grant_type=password`, `username=alice`, `password=alice`) verified against `C:\development\github\tiny-ledger-bootui-ref\docker\tls\ca.crt` (never `verify=False` or `curl -k`).
   - BootUI console API calls (`/bootui/api/*`) use BootUI's own guard on `http://127.0.0.1:8080/bootui/api/*` (loopback `127.0.0.1`, `Host: 127.0.0.1:8080`, plus `Authorization: Bearer <bootui.authentication.token>` or `POST /bootui/api/auth/session` `BOOTUI_SESSION` cookie when token auth is configured). Mixing the two tokens causes 401/403. Pinned by `test_golden_capture_manifest_has_all_2_2_0_panels_and_no_error_envelopes` in **Task 2**.
2. **Secret and volatile-field sanitisation in `scripts/sanitize_golden.py:19-68`**:
   - BootUI 2.2.0 adds `instanceId`, `runId`, `startedAt`, `checkedAt`, `oldestTimestamp`, `newestTimestamp`, and `durationMicros`. `sanitize_golden.py` must scrub any secret patterns (`find_secrets(data) == []`), normalize volatile IDs/timestamps, and write `"bootuiVersion": "2.2.0"` in `meta.json`. Pinned by `test_sanitize_golden_scrubs_2_2_0_volatile_keys_and_secrets` in **Task 2**.
3. **Live vs Provisional Golden separation (spec §6.1.1 & §12.11)**:
   - Any panel whose live capture cannot be triggered against `tiny-ledger-bootui-ref` (e.g., if a specific Spring subsystem is inactive) must be recorded in `meta.json` under `"provisional": ["<panel>"]` and built by a separate worker from BootUI 2.2.0 record definitions in `C:\development\github\boot-ui-ref\bootui-engine\src\main\java\io\github\jdubois\bootui\core\dto\`, never hand-authored by the panel implementer. Pinned by `test_conformance_2_2_0_goldens_and_ids_mapping` in **Task 2**.
4. **Integer-cent money invariants & optimistic locking in `tiny-ledger-py` (`design.md` §3)**:
   - `Money` must reject floats and negative/zero movement amounts, enforce scale = 2 (`BigDecimal` parity), and `Account` deposits/withdrawals must be idempotent by `depositUid`/`withdrawalUid` and raise HTTP 409 (`https://tiny-ledger.example.com/problems/optimistic-lock-conflict`) on concurrent version conflict. Pinned by `test_domain_money_and_account_invariants` and `test_optimistic_lock_conflict_returns_409_problem_detail` in **Task 3**.
5. **`sharpit.install(app, models=Base, engines=[engine])` route non-interference (`design.md` §6)**:
   - Mounting sharpit at `/sharpit` in `tiny-ledger-py` must not shadow `/api/v1/*` routes or alter RFC 7807 `application/problem+json` error responses, and `GET /sharpit/api/data` + `GET /sharpit/api/postgresql` must discover the 4 ledger tables (`events`, `account_summary`, `account_transactions`, `audit_log`). Pinned by `test_sharpit_mount_discovers_ledger_models_and_preserves_api_v1` in **Task 4**.

---

### Task 1 (G0a): Lease Reference Stack, Drive Seed Traffic via Keycloak JWT, and Capture Raw BootUI 2.2.0 Evidence

**Files:**
- Create: `replica/evidence/2.2.0/<panel>.json` (for all BootUI 2.2.0 panels + `panels.json` + `dismissed-findings.json`)
- Create: `.superpowers/sdd/0.4.0/lanes/G0/capture.log`

**Interfaces:**
- Consumes: `C:\development\github\tiny-ledger-bootui-ref\docker\docker-compose.yml`, `docker/tls/ca.crt`, `http://127.0.0.1:8080/bootui/api/*`.
- Produces: Raw JSON captures in `replica/evidence/2.2.0/*.json`.

- [ ] **Step 1: Join `agentctl.py` and lease reference stack ports (`5432`, `6379`, `9092`, `443`, `8080`)**
  - Run `python C:/Users/ffrol/.claude/skills/multi-agent-dev/scripts/agentctl.py join --repo sharpit --branch lane/G0 --task "G0a 2.2.0 goldens"` and lease `--global postgres-5432`, `--global redis-6379`, `--global kafka-9092`, `--global traefik-443`, and `app-port` `8080`.
  - Ensure `tiny-ledger-bootui-ref` Docker stack (`docker compose -f docker/docker-compose.yml up -d`) and `./gradlew bootRun` (on branch `chore/bootui-2.2.0-goldens`) are healthy (`GET http://127.0.0.1:8080/actuator/health` → `200 UP`).
- [ ] **Step 2: Obtain Keycloak token using `docker/tls/ca.crt` and seed ledger activity**
  - Using Python `httpx.Client(verify="C:/development/github/tiny-ledger-bootui-ref/docker/tls/ca.crt")`, POST to `https://auth.localhost/realms/tiny-ledger/protocol/openid-connect/token` with `data={"client_id": "ledger-test", "grant_type": "password", "username": "alice", "password": "alice"}`.
  - With `Authorization: Bearer <access_token>`, drive `POST /api/v1/accounts`, `PUT /api/v1/accounts/{uid}/deposits/{depUid}`, `PUT /api/v1/accounts/{uid}/withdrawals/{wdUid}`, `GET /api/v1/accounts/{uid}/balance?consistency=strong`, `GET /api/v1/accounts/{uid}/transactions`, plus one deliberate 422 overdraft and one 404 account lookup so `http-exchanges`, `sql-trace`, `exceptions`, `hibernate-statistics`, `transactions`, `caches`, `messaging`, and `postgresql` have rich runtime state.
- [ ] **Step 3: Authenticate to BootUI `/bootui/api/*` on `127.0.0.1:8080` and capture all 2.2.0 endpoints**
  - Connect to `http://127.0.0.1:8080/bootui/api` with `Host: 127.0.0.1:8080` (and `Authorization: Bearer <token>` or `BOOTUI_SESSION` cookie via `POST /bootui/api/auth/session` if `bootui.authentication.token` is set, per `BOOTUI-CONTRACT-MVP.md` §10).
  - Trigger explicit scan/read actions first (`POST /bootui/api/postgresql/read`, `POST /bootui/api/rest-api/scan`, `POST /bootui/api/vulnerabilities/scan`), then fetch and save every panel's GET JSON into `replica/evidence/2.2.0/<panel>.json` plus `panels.json`, `dismissed-rules.json`, `dismissed-findings.json`, `http-exchanges-routes.json`, and `exceptions-caught.json`.

---

### Task 2 (G0a): Update `scripts/sanitize_golden.py` for 2.2.0 and Populate `tests/fixtures/bootui/2.2.0/`

**Files:**
- Modify: `scripts/sanitize_golden.py:19-109`
- Create: `tests/fixtures/bootui/2.2.0/*.json`, `tests/fixtures/bootui/2.2.0/ids.json`, `tests/fixtures/bootui/2.2.0/*.nullable.json`, `tests/fixtures/bootui/2.2.0/meta.json`
- Modify: `tests/test_conformance.py`, `tests/test_sanitize_golden.py`

**Interfaces:**
- Produces in `scripts/sanitize_golden.py`: `sanitize(value: Any, key: str | None = None) -> Any` handling 2.2.0 volatile keys (`instanceId`, `runId`, `startedAt`, `checkedAt`, `oldestTimestamp`, `newestTimestamp`) and `--version 2.2.0` flag in `main()`.
- Produces `tests/fixtures/bootui/2.2.0/ids.json`:
  `{"flyway": "alembic", "hibernate-statistics": "sqlalchemy-statistics", "spring-security": "fastapi-security", "spring": "fastapi"}` (plus identity mappings for all other 0.4.0 panels per spec §6.2).

- [ ] **Step 1: Write failing tests in `tests/test_sanitize_golden.py` and `tests/test_conformance.py`**
  - `test_sanitize_golden_scrubs_2_2_0_volatile_keys_and_secrets`: verifies `instanceId` and `runId` normalize to `"00000000"`, `startedAt`/`checkedAt`/`oldestTimestamp`/`newestTimestamp` normalize to `1700000000000`, and `find_secrets` is empty.
  - `test_golden_capture_manifest_has_all_2_2_0_panels_and_no_error_envelopes`: verifies every 0.4.0 panel has a fixture in `tests/fixtures/bootui/2.2.0/`, `ids.json` maps every renamed panel, and no fixture is a guard `{"error": ...}` body.
- [ ] **Step 2: Run `uv run pytest -q tests/test_sanitize_golden.py tests/test_conformance.py` and verify RED**
- [ ] **Step 3: Update `scripts/sanitize_golden.py`, run it on `replica/evidence/2.2.0` → `tests/fixtures/bootui/2.2.0`, and write `ids.json` + `*.nullable.json`**
- [ ] **Step 4: Run `uv run pytest -q tests/test_sanitize_golden.py tests/test_conformance.py` and commit in `sharpit`** (`test(goldens): add sanitised BootUI 2.2.0 golden fixtures, ids.json, and nullable manifests`).

---

### Task 3 (G0b): `tiny-ledger-py` Increment 1 — Core Ledger, Alembic 001–006, and `/api/v1` Endpoints

**Files (all in `C:\development\github\tiny-ledger-py` on branch `feat/increment-1-ledger`):**
- Create: `pyproject.toml`, `alembic.ini`, `migrations/env.py`, `migrations/versions/001_init_event_store.py`..`006_index_events_global_index.py`
- Create: `src/tiny_ledger/settings.py`, `src/tiny_ledger/domain/{money.py,account.py,events.py,policy.py}`, `src/tiny_ledger/adapters/outbound/postgres/{models.py,repositories.py}`, `src/tiny_ledger/adapters/inbound/rest/{app.py,routes.py,problems.py}`, `src/tiny_ledger/application/ledger_service.py`
- Test: `tests/unit/test_domain.py`, `tests/integration/test_ledger_api.py`

**Interfaces:**
- Produces in `tiny_ledger`:
  - `Money(amount: Decimal)` (2 decimal places, non-negative, rejects `float`); `Account.deposit(uid, amount, description, now)`, `Account.withdraw(uid, amount, description, now)`.
  - SQLAlchemy 2 `Base` models `EventRow` (`events`), `AccountSummaryRow` (`account_summary`), `AccountTransactionRow` (`account_transactions`), `AuditLogRow` (`audit_log`).
  - FastAPI routes: `POST /api/v1/accounts` (201), `GET /api/v1/accounts` (200), `GET /api/v1/accounts/{accountUid}` (200/404), `PUT /api/v1/accounts/{accountUid}/deposits/{depositUid}` (200 idempotent), `PUT /api/v1/accounts/{accountUid}/withdrawals/{withdrawalUid}` (200/422), `GET /api/v1/accounts/{accountUid}/balance` (200), `GET /api/v1/accounts/{accountUid}/transactions` (200 keyset cursor), plus `501` RFC 7807 stub on `/events` and `/audit/entries` (`design.md` §2).

- [ ] **Step 1: Write failing unit and API tests in `C:\development\github\tiny-ledger-py\tests\`**
  - `test_domain_money_and_account_invariants`: pins integer-cent scale, idempotent deposit/withdrawal replay, overdraft rejection (`422`), and closed/frozen account rejection.
  - `test_optimistic_lock_conflict_returns_409_problem_detail`: pins RFC 7807 `application/problem+json` with `type="https://tiny-ledger.example.com/problems/optimistic-lock-conflict"`.
  - `test_standalone_profile_runs_full_account_lifecycle_without_docker`: exercises open → deposit → withdraw → balance → keyset transactions in `TINY_LEDGER_PROFILE=standalone`.
- [ ] **Step 2: Run `uv run pytest -q` in `C:\development\github\tiny-ledger-py` and verify RED**
- [ ] **Step 3: Implement domain, Alembic migrations 001–006, Postgres & standalone repositories, and FastAPI `/api/v1` routes**
- [ ] **Step 4: Run `uv run pytest -q` against both `standalone` and Docker Postgres (`localhost:5432`) and commit in `tiny-ledger-py`** (`feat(ledger): implement Increment 1 core ledger, Alembic 001-006, and /api/v1 endpoints`).

---

### Task 4 (G0b): `tiny-ledger-py` Increment 2 — Mount `sharpit.install(app)` and Enable `pytest --sharpit` Gate

**Files (all in `C:\development\github\tiny-ledger-py` on branch `feat/increment-2-sharpit`):**
- Modify: `pyproject.toml` (editable/path dependency on `sharpit`), `src/tiny_ledger/adapters/inbound/rest/app.py`
- Create: `tests/integration/test_sharpit_mount.py`

**Interfaces:**
- Produces in `src/tiny_ledger/adapters/inbound/rest/app.py`:
  - `sharpit.install(app, models=Base, engines=[engine])` mounted at `/sharpit` (`api_path="/sharpit/api"`).

- [ ] **Step 1: Write failing integration test `tests/integration/test_sharpit_mount.py` in `tiny-ledger-py`**
  - `test_sharpit_mount_discovers_ledger_models_and_preserves_api_v1`: verifies `/api/v1/accounts` works unchanged, `/sharpit/api/overview` and `/sharpit/api/panels` return 200 on loopback, and `/sharpit/api/http-exchanges` + `/sharpit/api/sql-trace` record the ledger requests.
- [ ] **Step 2: Run `uv run pytest -q tests/integration/test_sharpit_mount.py` and verify RED** (`404` on `/sharpit/api/overview`).
- [ ] **Step 3: Wire `sharpit.install(app, models=Base, engines=[engine])` in `create_app()` and configure `pytest --sharpit`**
- [ ] **Step 4: Lease port `8081` via `agentctl.py`, run live verification against `http://127.0.0.1:8081/sharpit/api/*`, and commit in `tiny-ledger-py`** (`feat(sharpit): mount sharpit console at /sharpit and enable pytest --sharpit gate`).

---

## Lane Evidence Checklist (`lane_gate.py` — Spec §10.3)

`.superpowers/sdd/0.4.0/lanes/G0/` MUST contain:
- [ ] `field-map.md` — Manifest of all captured 2.2.0 golden files, `ids.json` mappings, and every `<panel>.nullable.json` justification, plus any panel marked `"provisional": true` in `meta.json` (spec §6.1.1 & §12.11).
- [ ] `findings.md` — `finding → test → red` table with all rows `fixed` or `parked`.
- [ ] `checklist.md` — Verification log paths (`capture.log`, `sanitize.log`, `tiny-ledger-py-pytest.log`, `live-verify.log`) naming the head commit SHAs of both `sharpit` (G0a) and `tiny-ledger-py` (G0b).
- [ ] `handoff.md` — Current state of G0a and G0b, last green commands, open findings (`none`).
- [ ] `review.md` — Fresh reviewer subagent (`reviewer_id != implementer_id`) + `/code-review high` naming head SHA, ending with `VERDICT: APPROVE`.
