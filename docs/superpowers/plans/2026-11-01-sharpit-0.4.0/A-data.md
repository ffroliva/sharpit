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
| **Depends on** | F merged (§10.2: `implemented` flag, per-panel route modules, `SharpitContext.models`, golden loader + `ids.json`, `lane_gate.py`); D1 merged (envelope) |
| **May touch** | `src/sharpit/engine/collectors/data.py` (new), `src/sharpit/fastapi/routes/data.py` (F's stub for this panel), the `data` row F pre-registered (flip `implemented=True` only), the `get_data_*` MCP stub F created, `ui/src/views/Data.svelte` (new) + its test, `tests/engine/test_data.py`, `tests/fastapi/test_data_api.py`, `tests/fixtures/bootui/2.2.0/data/*`, `.superpowers/sdd/0.4.0/lanes/A-data/*` |
| **Must NOT touch** | §10.3 protected files (`scripts/dev/lane_gate.py`, `tests/complexity_baseline.json`, `sonar-baseline.txt`, rules in `tests/engine/test_import_boundary.py`, overhead budget constants, dependency lists in `pyproject.toml`/`uv.lock`); `src/sharpit/engine/sqla.py` (A-postgresql owns its edits); other lanes' modules; `src/sharpit/fastapi/adapter.py` beyond the line F reserved |

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

**Files:** Create `tests/fixtures/bootui/2.2.0/data/repositories.json`, `.../data/repository-detail.json`,
`.../data/nullable.json`; Test `tests/fastapi/test_data_api.py` (parity test only, skipped-red until Task 4).

**Interfaces:** Consumes F's golden loader (expected `tests/golden.py::assert_parity(sharpit_id: str, name: str,
payload: dict[str, Any]) -> None`; if F named it differently, use F's name and fix this line in the commit) and
`tests/fixtures/bootui/2.2.0/ids.json` (`"data": "data"`).

- [ ] **Step 1:** If G0 captured `data` from tiny-ledger-bootui, sanitise with `scripts/sanitize_golden.py`; else ask
  the coordinator for a **provisional** fixture from another worker (§6.1.1, §12.11) and mark it so in `checklist.md`.
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
    sqla.UNAVAILABLE`.
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

**Files:** Modify `src/sharpit/fastapi/routes/data.py` (F's stub), the `data` `Panel` row (`implemented=True`,
`action_capable=False`, `api_prefix="/data"`), the `get_data_repositories` MCP stub F created; Test
`tests/fastapi/test_data_api.py`, `tests/test_safety_matrix.py` (add rows only).

**Interfaces:** `GET {api}/data/repositories` → `repositories_report`; `GET {api}/data/repositories/{name}` → detail
or **404 empty body** (contract §1). MCP `get_data_repositories` (read, `action=False`).

- [ ] **Step 1:** Tests: `test_repositories_golden_parity` (`assert_parity("data", "repositories", body)`),
  `test_detail_404_empty_body`, `test_get_has_no_side_effects` (uses `no_side_effects`; also asserts
  `configure_mappers` not called, via the Task 2 spy), `test_panel_disabled_403` (`SHARPIT_PANELS_DATA_ENABLED=false` →
  `{"error":"sharpit panel access denied","panel":"data","reason":disabled_reason("data")}`),
  `test_panel_listed_when_implemented` (`/panels` contains `data`, `actionCapable` false), `test_mcp_lists_read_tool_only`.
- [ ] **Step 2:** FAIL (404 from the unimplemented stub — that is an assertion on status, acceptable red).
- [ ] **Step 3:** Fill the route module; flip `implemented`. **Step 4:** PASS + full gate in background. Commit
  `feat: data panel routes and MCP read tool`.

### Task 5: Svelte view

**Files:** Create `ui/src/views/Data.svelte`, `ui/src/views/Data.test.ts`; Modify the nav entry F pre-registered (flag
only).

- [ ] **Step 1:** vitest `Data.test.ts`: renders rows from a fixture copy of `repositories.json`; shows
  `unavailableReason` text when `springDataPresent` false; detail drawer lists relationships with `lazy`; `null`
  counts render as "—", never "0". BootUI `views/Data.vue` is the behavioural reference.
- [ ] **Step 2:** `npm --prefix ui test -- Data` FAIL. **Step 3:** implement with existing `ui/src/lib` loaders.
- [ ] **Step 4:** `npm --prefix ui run check` and tests PASS (no `npm run build`). Commit `feat: data panel view`.

### Task 6: Live check, docs, lane evidence

**Files:** `examples/fastapi_sqla/` (pass `models=Base` in its `install` call), `skills/sharpit/SKILL.md` (one row),
`docs/reference/BOOTUI-CONTRACT-0.4-WAVE-A.md` (no edit; cite), `.superpowers/sdd/0.4.0/lanes/A-data/*`.

- [ ] **Step 1:** `test_example_app.py` gains `test_example_data_panel_lists_models` (red first: example has no
  `models=`).
- [ ] **Step 2:** `/sharpit:live-verify` on `examples/fastapi_sqla` (port from `agentctl lease app-port`); record
  requests and responses in `live-verify.md`; repeat on tiny-ledger-py if its increment exists.
- [ ] **Step 3:** lowest-direct and no-SQLAlchemy jobs in a throwaway copy, logs naming the head SHA.
- [ ] **Step 4:** Commit `docs: data panel usage and lane evidence`.

## §6.1 definition of done → task

| §6.1 item | Satisfied by |
|---|---|
| 1 golden parity, `nullable.json`, field map | Task 1, Task 4 `test_repositories_golden_parity`, field map above |
| 2 `# ported:` citations | Tasks 2–3 |
| 3 safety: `no_side_effects`, `PANELS`, env flags, guard unchanged, masking | Task 4 (no new secret source: class/table names only; `test_panel_disabled_403`) |
| 4 gatekeeper | Task 2 (no SQLAlchemy import; boundary test unchanged and green) |
| 5 overhead budget | n/a: no hot path (stated in `checklist.md`) |
| 6 MCP read-only | Task 4 `test_mcp_lists_read_tool_only` |
| 7 Svelte view | Task 5 |
| 8 four gates + lowest-direct + no-SQLAlchemy | Task 4 Step 4, Task 6 Step 3 |
| 9 live check | Task 6 Step 2 |
| 10 handoff current | every commit |

## Lane evidence checklist (`.superpowers/sdd/0.4.0/lanes/A-data/`)

`handoff.md` (last green command, next step, open findings) · `field-map.md` · `checklist.md` (the table above with evidence
paths) · `findings.md` (`finding → test → red output`, each row `fixed` or `parked`) · `review.md` (last line
`VERDICT: APPROVE`, reviewer id ≠ implementer id, head SHA) · `gate/` (four gates, lowest-direct and
no-SQLAlchemy logs, each naming the head SHA) · `live-verify.md`. File names follow `lane_gate.py` on `release/0.4.0` if it names them differently.
