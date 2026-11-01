# Lane A-data: the `data` panel (SQLAlchemy mapped classes)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes.

| | |
|---|---|
| **Lane id** | `A-data` (worktree `C:\development\github\sharpit-wt\0.4.0-A-data`, branch `lane/0.4.0-A-data` from `release/0.4.0`) |
| **Goal** | `GET /sharpit/api/data/repositories` lists the app's SQLAlchemy mapped classes in BootUI's `RepositoriesReport` shape, from `install(models=...)` only, without ever configuring a mapper. |
| **Spec** | `docs/superpowers/specs/2026-11-01-sharpit-0.4.0-design.md` §4 (anti-goals), §6.1–§6.3, §7 row `data`, §11, §12.5 |
| **Contract** | `docs/reference/BOOTUI-CONTRACT-0.4-WAVE-A.md` §1; BootUI `DataController.java`, `RepositoriesReport`, `RepositoryDto`, `RepositoryDetailDto`, `RepositoryMethodDto` |
| **Worker** | M, mostly mechanical; one judgement point (the `mapper.configured` guard) |
| **Depends on** | F (PLAN.md). Consumes these rows of F's consumer interface table (`F-foundation.md`): "implemented flag files" (`engine/panels04/<id>.py` + `ui/src/lib/panels04/<id>.ts`, O4 flag files, here `data`), `sharpit.fastapi.routes.<id>` (`routes/data.py`), `sharpit.install` / `SharpitContext.models`, `tests.golden.assert_parity` (O2 loader) + `ids.json`, `sharpit.engine.tool_stubs.<id>`, the `ui/src/views/Data.svelte` placeholder, `scripts/dev/lane_gate.py`; the `examples/fastapi_sqla` wiring F does once (O3: `install(models=Base)`). `tests/safety/` + `tests/masking/` are F-rest pieces: if not merged when this lane starts, the lane creates its own `tests/safety/test_a_data_safety.py` without shared helpers |
| **May touch** | `src/sharpit/engine/collectors/data.py` (new), `src/sharpit/fastapi/routes/data.py` (F's stub for this panel), `src/sharpit/engine/panels04/data.py` and `ui/src/lib/panels04/data.ts` (flip the flag only, O4), `src/sharpit/engine/tool_stubs/data.py` (F-rest's MCP stub; the lane creates it if F-rest has not merged), `ui/src/views/Data.svelte` (replace F's placeholder only) + `Data.test.ts`, `tests/engine/test_data.py`, `tests/fastapi/test_data_api.py`, `tests/safety/test_a_data_safety.py`, `tests/fixtures/bootui/2.2.0/data/nullable.json` (O2: the lane owns only this fixture), the implementer files in `.superpowers/sdd/0.4.0/lanes/A-data/` (C2) plus `docs.md` there (O3) |
| **Must NOT touch** | §10.3 protected files (`scripts/dev/lane_gate.py`, `tests/complexity_baseline.json`, `sonar-baseline.txt`, rules in `tests/engine/test_import_boundary.py`, overhead budget constants, dependency lists in `pyproject.toml`/`uv.lock`); `src/sharpit/engine/sqla.py` (O1: A-postgresql); other lanes' modules; `src/sharpit/fastapi/adapter.py`; `PANELS` in `engine/panels.py`, `ui/src/App.svelte`, `ui/src/lib/nav.ts`, `ui/src/lib/types.ts` (O4); `captured.json` / `provisional.json` under `tests/fixtures/bootui/` (O2: G0a / another worker); `README.md`, `skills/sharpit/SKILL.md`, `examples/fastapi_sqla/`, `tests/test_example_app.py` (O3); `tests/test_safety_matrix.py`, `tests/test_masking_corpus.py` (C5); any `review.md` or `gate/` path |

**Architecture:** One framework-free collector (`engine/collectors/data.py`) that walks the objects passed in
`models=` by duck-typed public attributes; it imports nothing from SQLAlchemy (gatekeeper rule 4 holds trivially; if a
helper needs the module it calls `sqla.sqlalchemy_module()`, never `import sqlalchemy`). The FastAPI route module only
serialises. No GET opens a connection: mapper metadata is in-process.

## Global Constraints (AGENTS.md, verbatim where it matters)

- Runtime deps exactly `starlette` and `packaging`. SQLAlchemy only through `engine/sqla.py`.
- "No GET route and no MCP tool may open a socket, write a file, change a logger level or change `os.environ`." §4 adds:
  run SQL, call user code, **configure ORM mappers**.
- Every contract DTO key emitted (nulls included), camelCase, no envelope. Error strings verbatim with `BootUI`→`sharpit`.
- Each ported test cites `# ported: DataControllerTests.<method>`; derived tests `# derived: <reason>`.
- A red is an assertion, never a crash: Step 1 of each task stubs every Produces name first.
- One condition per assert (PT018). No module over 1000 lines; ratchets only go down.
- Commits: conventional prefix, explicit `git add` paths, no AI attribution. Long commands in the background.

## Review Focus

1. **An unconfigured mapper on a GET.** `models=` given before the app's first query, so mappers are not configured;
   touching `mapper.relationships`/`mapper.attrs` would run `configure_mappers()` (user code, may raise). Expect
   `unavailableReason` naming the class, no configure. Pinned in Task 2: `test_unconfigured_mapper_is_not_configured`.
2. **A broken mapping elsewhere in the registry** (a relationship to a missing class). Expect the other classes still
   listed only if configured; never an exception out of the GET. Pinned in Task 2: `test_broken_registry_degrades`.
3. **Odd `models=` inputs**: a `registry`, a declarative base, a list mixing both, the same registry twice, an object
   that is neither. Expect each mapped class once, sorted, and a warning for the stranger. Pinned in Task 2:
   `test_models_forms_dedupe`.
4. **Detail lookup ambiguity**: two classes with the same simple name in different modules. Expect lookup by FQ name
   to work and by simple name to return the first in sorted order, as BootUI. Pinned in Task 3:
   `test_detail_simple_name_collision`.
5. **SQLAlchemy not imported / older than 2.0.** Expect `springDataPresent:false` + `sqla.unavailable_reason()` text,
   no import. Pinned in Task 2: `test_sqlalchemy_absent`.

## Field map (lane report copies this to `field-map.md`)

| BootUI key | Python source |
|---|---|
| `springDataPresent` | `True` when `models=` resolves to ≥1 registry and SQLAlchemy ≥2 is imported |
| `total` | `len(repositories)` |
| `beanName` | class `__qualname__` |
| `repositoryInterface` | `f"{cls.__module__}.{cls.__qualname__}"` |
| `domainType` | same FQ name (the class is the domain type) |
| `idType` | primary-key column types, `", ".join(type(col.type).__name__ for col in mapper.primary_key)`; `null` if none |
| `storeModule` | `"SQLAlchemy"` |
| `customImplementation` | `null` (no analogue; String, nullable by type) |
| `queryMethodCount`, `fragmentCount` | `null` + `nullable.json` reason `"SQLAlchemy has no repository methods"` |
| `origin` (detail methods) | `"APPLICATION"` per spec §7 (one row per relationship, see Task 3) |
| extra `table` | `mapper.local_table.fullname` or `null` |
| extra `relationships` | `[{name, target, lazy}]` (`rel.key`, FQ target, `rel.lazy`), only when `mapper.configured` |

---

### Task 1: Golden fixture, nullable keys, id mapping

**Files:** Create `tests/fixtures/bootui/2.2.0/data/nullable.json`; Test `tests/fastapi/test_data_api.py` (parity
test only, skipped-red until Task 4).

**Interfaces:** Consumes F's golden loader `tests/golden.py::assert_parity(sharpit_id: str, name: str, payload:
Mapping[str, Any]) -> None` and `tests/fixtures/bootui/2.2.0/ids.json` (`"data": "data"`). Per O2 (amends C3), `data`
is a multi-endpoint panel: the loader reads `tests/fixtures/bootui/2.2.0/data/repositories.captured.json` and
`.../data/repository-detail.captured.json` (written by G0a only) when present, else `<name>.provisional.json` (written by
a worker other than this lane) and marks the result unverified. The lane writes only `nullable.json`.

- [ ] **Step 1:** If G0a's `captured.json` files for `data` exist, use them; else ask the coordinator for
  **provisional** fixtures from another worker (§6.1.1, §12.11) and record "unverified" in `checklist.md` item 1.
- [ ] **Step 2:** Write `nullable.json`: `{"repositories[].queryMethodCount": "SQLAlchemy has no repository methods",
  "repositories[].fragmentCount": "SQLAlchemy has no repository fragments"}`.
- [ ] **Step 3:** Commit `test: data panel golden fixture and nullable keys`.

### Task 2: Collector `engine/collectors/data.py`

**Files:** Create `src/sharpit/engine/collectors/data.py`; Test `tests/engine/test_data.py`.

**Interfaces:** Consumes `SharpitContext.models: tuple[object, ...]` (F), `sqla.unavailable_reason()`
(`engine/sqla.py:52`), `ctx.masker`. Produces:
- `NO_MODELS = "pass models= to sharpit.install"` (exact, spec §7)
- `UNCONFIGURED = "Mappers are not configured yet: the app has not run a query"` (sharpit text; logged §11)
- `registries(models: Sequence[object]) -> tuple[list[object], list[str]]` — `(registries, warnings)`; a declarative
  base → `base.registry`; a `registry` → itself (duck-typed: has `.mappers`); duplicates by identity dropped.
- `repositories_report(ctx: SharpitContext) -> dict[str, Any]` — `{springDataPresent, total, repositories,
  unavailableReason, warnings}` (`unavailableReason`/`warnings` are extra keys, logged §11).
- `repository_detail(ctx: SharpitContext, name: str) -> dict[str, Any] | None`

- [ ] **Step 1:** Stub the Produces names. Write tests (sqlite in-memory declarative models built in the test):
  - `test_lists_one_row_per_mapped_class` — `# ported: DataControllerTests.repositoriesReturnsSummaryForDiscoveredRepository`;
    asserts `report["total"] == 2`, row keys equal the golden's key set plus `table`, `relationships`,
    `row["storeModule"] == "SQLAlchemy"`, `row["idType"] == "Integer"`.
  - `test_no_models_is_unavailable` — `# ported: DataControllerTests.repositoriesReturnsEmptyReportWhenNoBeanFactory`;
    `models=()` → `springDataPresent is False`, `unavailableReason == NO_MODELS`, `repositories == []`.
  - `test_empty_registry` — `# ported: DataControllerTests.repositoriesReturnsEmptyReportWhenNoRepositoryBeans`.
  - `test_unconfigured_mapper_is_not_configured` — patch `sqlalchemy.orm.configure_mappers` and
    `Mapper._check_configure` to record calls; build models, do **not** query; call `repositories_report`; assert no
    call recorded; assert the row's `relationships is None`; assert `UNCONFIGURED` in `warnings`.
  - `test_broken_registry_degrades` — a relationship to `"Missing"`; report returns, no exception.
  - `test_models_forms_dedupe` — `[Base, Base.registry, Base]` → each class once; `object()` → one warning.
  - `test_sqlalchemy_absent` — `monkeypatch.delitem(sys.modules, "sqlalchemy")` → `unavailableReason ==
    sqla.UNAVAILABLE` (`engine/sqla.py:37`; `sqla.unavailable_reason()` at `:52` returns it).
- [ ] **Step 2:** `uv run --no-sync pytest -q tests/engine/test_data.py` → FAIL on the named assertions.
- [ ] **Step 3:** Implement. Read only `registry.mappers`, `mapper.class_`, `mapper.configured`, `mapper.primary_key`,
  `mapper.local_table`; `mapper.relationships` only behind `if mapper.configured`. Rows sorted by
  `repositoryInterface`. Every attribute read wrapped so one bad mapper drops only its own row (warning).
- [ ] **Step 4:** Tests PASS. Commit `feat: data collector over install(models=)`.

### Task 3: Detail lookup

**Files:** Modify `src/sharpit/engine/collectors/data.py`; Test `tests/engine/test_data.py`.

**Interfaces:** `repository_detail` returns `RepositoryDetailDto` keys `beanName, repositoryInterface, domainType,
idType, storeModule, customImplementation, methods, fragments` (+ `table`). `methods` = one `RepositoryMethodDto` per
relationship: `{name: rel.key, signature: f"{rel.key} -> {Target}", origin: "APPLICATION", query: None, nativeQuery:
False, namedQuery: None}`; empty when unconfigured. `fragments = []`.

- [ ] **Step 1:** Tests `test_detail_by_bean_name`, `test_detail_by_fq_name`, `test_detail_by_simple_name`
  (`# ported: DataControllerTests.repositoryDetailLooksUpByBeanName` / `...ByFullyQualifiedInterfaceName` /
  `...BySimpleInterfaceName`), `test_detail_unknown_is_none` (`# ported: ...repositoryDetailReturnsNotFoundForUnknownRepository`),
  `test_detail_simple_name_collision` (two `User` classes in two modules: FQ lookup returns each; simple returns the
  sorted-first).
- [ ] **Step 2:** FAIL on assertions. **Step 3:** implement. **Step 4:** PASS; commit `feat: data repository detail`.

### Task 4: Routes, panel flag, MCP read tool, safety

**Files:** Modify `src/sharpit/fastapi/routes/data.py` (F's stub), `src/sharpit/engine/panels04/data.py`
(`IMPLEMENTED = True`, O4; F's pre-registered `data` row in `PANELS` already reads it with `action_capable=False`,
`api_prefix="/data"`; `Panel` at `engine/panels.py:11`), the `get_data_repositories` MCP stub (F-rest's, or the lane's own if absent) in
`src/sharpit/engine/tool_stubs/data.py`; Test `tests/fastapi/test_data_api.py`, `tests/safety/test_a_data_safety.py` (this lane's safety rows, on F-rest's
shared helpers; C5).

**Interfaces:** `GET {api}/data/repositories` → `repositories_report`; `GET {api}/data/repositories/{name}` → detail
or **404 empty body** (contract §1). MCP `get_data_repositories` (read, `action=False`).

- [ ] **Step 1:** Tests: `test_repositories_golden_parity` (`assert_parity("data", "repositories", body)`),
  `test_detail_404_empty_body`, `test_get_never_configures_mappers` (canonical, PLAN.md Review Focus 5: both GETs
  under `no_side_effects` with an **unconfigured** registry; asserts the Task 2 spy saw no `configure_mappers` /
  `Mapper._check_configure` call and no statement was issued), `test_panel_disabled_403`
  (`SHARPIT_PANELS_DATA_ENABLED=false` → `{"error":"sharpit panel access denied","panel":"data","reason":
  disabled_reason("data")}`; `PANEL_ACCESS_DENIED` at `engine/guard.py:42`, `disabled_reason` at `engine/panels.py:48`),
  `test_panel_listed_when_implemented` (`/panels` contains `data`, `actionCapable` false), `test_mcp_lists_read_tool_only`.
- [ ] **Step 2:** FAIL on the status assertion (F's unimplemented panel answers 404; `assert response.status_code ==
  200` names it); never an `ImportError` (C4).
- [ ] **Step 3:** Fill the route module; flip `IMPLEMENTED` in `engine/panels04/data.py`. **Step 4:** PASS + full gate in background. Commit
  `feat: data panel routes and MCP read tool`.

### Task 5: Svelte view

**Files:** Replace F's placeholder `ui/src/views/Data.svelte`; create `ui/src/views/Data.test.ts`; set `implemented = true` in
`ui/src/lib/panels04/data.ts` (O4; `nav.ts`, `App.svelte`, `types.ts` untouched).

- [ ] **Step 1:** vitest `Data.test.ts`: renders rows from a copy of the `repositories` golden (`captured.json` or `provisional.json`, O2); shows
  `unavailableReason` text when `springDataPresent` false; detail drawer lists relationships with `lazy`; `null`
  counts render as "—", never "0". BootUI `views/Data.vue` is the behavioural reference.
- [ ] **Step 2:** `npm --prefix ui test -- Data` FAIL. **Step 3:** implement with existing `ui/src/lib` loaders.
- [ ] **Step 4:** `npm --prefix ui run check` and tests PASS (no `npm run build`). Commit `feat: data panel view`.

### Task 6: Live check, docs, lane evidence

**Files:** `.superpowers/sdd/0.4.0/lanes/A-data/docs.md` (O3: the SKILL/README row for `data` and the `models=`
usage, merged by PLAN Step 5), `docs/reference/BOOTUI-CONTRACT-0.4-WAVE-A.md` (no edit; cite), the implementer evidence
files (C2). No edit to `examples/fastapi_sqla/`, `tests/test_example_app.py`, `README.md` or `skills/sharpit/SKILL.md`
(O3: F already passes `models=Base` in the example's `install` call).

- [ ] **Step 1:** Write `docs.md`: one SKILL table row and a three-line `install(models=Base)` snippet.
- [ ] **Step 2:** `/sharpit:live-verify` on `examples/fastapi_sqla` as F wired it (port from `agentctl lease app-port`); record
  requests and responses in `handoff.md` §Live check and point `checklist.md` item 9 at it; repeat on tiny-ledger-py if
  its increment exists. `live-verify.md` is the coordinator's (C2).
- [ ] **Step 3:** lowest-direct and no-SQLAlchemy as a local pre-check (commands in `checklist.md` item 8); the gated
  logs are re-run and written by the coordinator in the integration worktree (C2).
- [ ] **Step 4:** Commit `docs: data panel usage and lane evidence`.

## §6.1 definition of done → task (spec order; `checklist.md` adds the evidence paths)

| §6.1 item | Satisfied by |
|---|---|
| 1 golden parity, `nullable.json`, field map | Task 1, Task 4 `test_repositories_golden_parity`, field map above |
| 2 `# ported:` citations | Tasks 2–3 |
| 3 safety: `no_side_effects`, `PANELS`, env flags, guard unchanged, masking | Task 4 (`test_get_never_configures_mappers`, `test_panel_disabled_403`, rows in `tests/safety/test_a_data_safety.py`); masking `N/A`: no new secret source (class/table names only) |
| 4 gatekeeper | Task 2 (no SQLAlchemy import; boundary test unchanged and green) |
| 5 overhead budget | `N/A`: no hot path |
| 6 MCP read-only | Task 4 `test_mcp_lists_read_tool_only` |
| 7 Svelte view | Task 5 |
| 8 four gates + lowest-direct + no-SQLAlchemy | Task 4 Step 4, Task 6 Step 3 (gated logs: coordinator) |
| 9 live check | Task 6 Step 2 (on F's example wiring) |
| 10 handoff current | every commit |

## Lane evidence (C2: `.superpowers/sdd/0.4.0/lanes/A-data/`)

- **Implementer, in the lane worktree:** `handoff.md` (last green command, next step, open findings, live-check
  requests), `findings.md` (`finding → test → red output`, each row `fixed` + red-test name or `parked` + reason),
  `field-map.md` (the field map above), `checklist.md` (the ten §6.1 items above in the spec's order, each with an evidence
  path or `N/A` + reason).
- **Coordinator/reviewer, in the integration worktree only:** `review.md` (`VERDICT: APPROVE`, reviewer id ≠
  implementer id, head SHA), `gate/{ruff-check,ruff-format,pyright,pytest,lowest-direct,no-sqlalchemy}.log`,
  `live-verify.md`. This lane's diff never touches any `review.md` or `gate/` path (`lane_gate.py` refuses it).
