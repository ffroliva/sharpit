# F — Foundation Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans. One task at a time; this lane is first and behaviour-neutral.

**Goal:** Prepare the 0.4.0 integration branch with responsibility splits, inert panel stubs, shared hook points, fixtures, and a mechanical lane gate while preserving the exact current test behavior.

**Architecture:** Split the three oversized owners by responsibility, keeping compatibility imports and hook behavior unchanged. Pre-register new panel ids as unimplemented so registries, routes, MCP, CLI, and nav cannot expose them until an owning lane flips its flag. Add shared test/document infrastructure without enabling any feature.

**Tech Stack:** Python 3.12+, pytest/pytester, Starlette, Svelte 5/TypeScript; no new runtime dependency.

**Spec:** `docs/superpowers/specs/2026-11-01-sharpit-0.4.0-design.md` §§10.2–10.3, 10.6; panel contract §6.1; lane order §13.

## Header and ownership

- **Lane:** F (foundation; must merge before any fan-out).
- **Worker profile:** L, judgement-heavy (responsibility splits, import behavior, gate safety).
- **Dependencies:** None; branch from the approved integration base. All G and panel lanes depend on this merge.
- **May touch:** `src/sharpit/fastapi/adapter.py` and new `fastapi/` responsibility modules; `src/sharpit/engine/tools.py` and new tool modules; `src/sharpit/pytest_plugin/__init__.py` and new plugin modules; `engine/panels.py`, settings/registries, capture wiring, `engine/sqla.py`; `ui/src/` navigation; `tests/` for parity and stubs; `tests/engine/test_import_boundary.py` (foundation gatekeeper rows only); `AGENTS.md` where §10.2 requires; `pyproject.toml`, `uv.lock` (only specified test dependencies); both testsession report schema copies; `docs/reference/bootui/2.2.0/`; `docs/reference/PARITY.md`; `scripts/dev/lane_gate.py`, its tests, and handoff template under `.superpowers/sdd/0.4.0/`.
- **Must not touch:** Later lane-owned feature implementation or panel modules; `tests/complexity_baseline.json`, `sonar-baseline.txt`, overhead budget constants, existing behavior assertions except equivalent coverage; dependency lists except OTel SDK and MySQL test driver with synchronized lock entries. `lane_gate.py` must refuse downstream changes to itself and protected files (§10.3).

## Global constraints

- Preserve public behavior exactly: full-suite result and observed behavior before/after F must match.
- `implemented=False` panels are absent from `/panels`, MCP `tools/list`, CLI, routes, and nav; their routes answer 404.
- Runtime dependencies remain exactly `starlette` and `packaging`; OTel SDK and MySQL driver are test-only.
- No module under `src/` may exceed 1000 lines. Keep engine framework-free and gatekeeper boundaries explicit.
- No new GET/MCP side effects; all new hooks and panel stubs remain inert.

## Review Focus

1. A split changes hook ordering or exception behavior: `test_foundation_suite_equivalence` asserts route registration, tool listing/dispatch, option resolution, report and exit behavior.
2. A parked panel appears through one surface: `test_unimplemented_panel_absent_from_all_surfaces` checks API, MCP, CLI and nav; `test_unimplemented_panel_route_404` checks routes.
3. Compatibility re-exports break a direct import or monkeypatch target: add targeted compatibility import tests for adapter, tools and pytest plugin facades.
4. A downstream lane bypasses evidence or alters protected files: refusal tests named in Task 4.
5. Report schema copies drift: extend `tests/test_report_schema.py::test_schema_copies_identical` to the paired copies.

---

### Task 1: Split oversized owners without behavior change

**Files:** Modify `src/sharpit/fastapi/adapter.py` (currently 787 lines), `src/sharpit/engine/tools.py` (800), `src/sharpit/pytest_plugin/__init__.py` (737); create responsibility modules under the same packages; add targeted tests under `tests/fastapi/`, `tests/engine/`, and `tests/pytest_plugin/`.

**Interfaces:** Preserve existing exported names and imports. Extract definitions with their current signatures; compatibility facades re-export names relied on by callers/tests. Record moved ownership in module docstrings. Keep hook order and routes unchanged.

- [ ] **Step 1: Pin current behavior.** Add `test_foundation_suite_equivalence` coverage for route registration, tool listing/dispatch, pytest option resolution and session report/exit behavior. Assert observable values and ordering, not module layout.
- [ ] **Step 2: Run the new assertions on the unmodified behavior.** Expected: PASS. Save the baseline full-suite command result and base SHA in the F handoff.
- [ ] **Step 3: Split by responsibility.** Extract cohesive adapter install/routes, tool registration/dispatch, and pytest options/gate/report/summary units; keep compatibility imports.
- [ ] **Step 4: Verify parity.** Run the same four gates at the new head and compare test collected/pass/fail/skip counts and targeted assertions to the recorded base. Any delta blocks F.
- [ ] **Step 5: Commit** `refactor: split foundation modules without behavior change`.

### Task 2: Add inert panel registration and shared extension points

**Files:** Modify `src/sharpit/engine/panels.py`, `src/sharpit/settings.py`, advisor/capture/discovery registries, `src/sharpit/engine/sqla.py`, post-split adapter/plugin/tools modules, `ui/src/`; corresponding `tests/`; `tests/engine/test_import_boundary.py`; `AGENTS.md` only for §10.2 gatekeeper rows.

**Interfaces:** `Panel` gains `implemented: bool = True`. `install(models=...)` stores `SharpitContext.models`. Add inert SQLAlchemy connection-event slot, capture middleware 401/403 callback, and span-processor wiring slot. Add pytest options `--sharpit-report-only`, `--sharpit-baseline`, `--sharpit-write-baseline` (accepted, inert). Every §6.2 0.4 id is registered with `implemented=False`, including Python stand-ins, settings/advisors/capture/discovery/MCP/nav stubs. Per-panel route modules are included only when implemented.

- [ ] **Step 1: Failing tests.** `test_unimplemented_panel_absent_from_all_surfaces`, `test_unimplemented_panel_route_404`, `test_panel_implemented_default_true`, `test_models_hook_stores_models_without_side_effects`, and option tests proving the three flags parse but do not alter session behavior.
- [ ] **Step 2: Run tests; expected named assertion failures** for missing field/registrations/hooks/options, never collection errors.
- [ ] **Step 3: Implement inert registrations and extension slots.** New paths remain dormant until an owning lane sets its panel `implemented=True`.
- [ ] **Step 4: Run targeted tests and four gates.** Every unimplemented id remains absent from every surface.
- [ ] **Step 5: Commit** `feat: add inert 0.4 panel and extension stubs`.

### Task 3: Add BootUI golden infrastructure and synchronized schemas

**Files:** Create `tests/fixtures/bootui/2.2.0/ids.json`, golden loader helper under `tests/`, `.superpowers/sdd/0.4.0/handoff-template.md`; modify `src/sharpit/engine/testsession/report.schema.json` and `docs/reference/report.schema.json`; tests under `tests/`.

**Interfaces:** `ids.json` maps BootUI ids to sharpit ids per §6.2. Loader resolves panel golden and optional adjacent `nullable.json`; provisional fixture metadata is retained for parity accounting. Schema files stay byte-identical.

- [ ] **Step 1: Failing tests.** `test_golden_id_mapping_covers_panel_ids`, `test_golden_loader_reads_nullable_reasons`, `test_provisional_fixture_is_not_counted_as_parity`, `test_schema_copies_identical`.
- [ ] **Step 2: Run tests; expected assertion failures.**
- [ ] **Step 3: Implement mapping, loader, template and paired schema update.**
- [ ] **Step 4: Run fixture/schema tests; expect id mapping and nullability to load, provisional fixture marked unverified, copies byte-equal.**
- [ ] **Step 5: Commit** `test: add BootUI 2.2 golden and handoff infrastructure`.

### Task 4: Implement the downstream mechanical lane gate

**Files:** Create `scripts/dev/lane_gate.py`, `tests/scripts/test_lane_gate.py`, `.superpowers/sdd/0.4.0/lanes/README.md` (evidence layout).

**Interfaces:** `main(argv: Sequence[str] | None = None) -> int`. Accept integration checkout, lane worktree, lane id and expected SHA. Validate a different reviewer id and matching head SHA; all findings fixed with red-test name or parked with reason; field map; current handoff; §6.1 checklist/evidence paths; forbidden-diff paths. **Re-run the four gates itself** at the lane head (`uv run ruff check`, `uv run ruff format --check`, `uv run pyright`, `uv run pytest -q -n auto`, each with a timeout, output saved under the lane's `gate/` folder with the SHA in the first line); only the lowest-direct and no-SQLAlchemy logs are read from files, and they must name the head SHA. `--no-rerun` exists for the refusal tests only and is refused when the lane id is not a test fixture. Coordinator executes the copy on integration checkout (§10.3).

- [ ] **Step 1: Failing refusal tests.** With a minimal valid fixture, assert exact refusal and nonzero exit for `test_lane_gate_refuses_missing_verdict`, `test_lane_gate_refuses_wrong_reviewer_or_sha`, `test_lane_gate_refuses_unresolved_finding`, `test_lane_gate_refuses_missing_field_map_handoff_or_checklist`, `test_lane_gate_refuses_protected_diff`, `test_lane_gate_refuses_gate_log_for_other_sha`, `test_lane_gate_refuses_when_rerun_gate_fails` (a fixture lane whose ruff check fails), `test_lane_gate_no_rerun_refused_for_real_lane`; control: `test_lane_gate_accepts_complete_evidence`.
- [ ] **Step 2: Run tests; expected assertion failures** from currently absent gate behavior.
- [ ] **Step 3: Implement deterministic evidence and diff checks.** Refuse gate script, complexity/sonar baselines, pre-existing import-boundary rules, overhead constants, `uv.lock` and dependency-list changes downstream; allow only F-authored import-boundary rows in F’s own diff.
- [ ] **Step 4: Run gate tests; expect every refusal and valid control to pass.**
- [ ] **Step 5: Commit** `feat: add mechanical 0.4 lane merge gate`.

### Task 5: Apply the F time box and write handoff

- [ ] **Step 1:** At T0 + 2 h, if F is not merged, cut to minimum required by committed lanes: splits, `implemented`, lane gate. Record every cut in handoff (§10.6).
- [ ] **Step 2:** Write `.superpowers/sdd/0.4.0/lanes/F/handoff.md` with base/head SHA, parity evidence, touched files, next step and open findings.
- [ ] **Step 3: Commit** `docs: record foundation lane handoff`.

### Foundation file map and guardrails

| Concern | Owner after split | Compatibility requirement |
|---|---|---|
| FastAPI install/route wiring | New focused modules under `src/sharpit/fastapi/` | `sharpit.install` and current imports stay stable |
| MCP/CLI tool definitions | New focused modules under `src/sharpit/engine/` | tool names, schemas, ordering and dispatch results stay stable |
| pytest options and session flow | Focused modules under `src/sharpit/pytest_plugin/` | hook registration and option defaults stay stable |
| Future panel exposure | `engine/panels.py` plus each surface’s existing registry | false means absent everywhere, including direct route paths |

- [ ] **Step 1:** Verify all newly created panel routes are mounted only through their per-panel route module and the `implemented` check; no shared route list is owned by a later lane.
- [ ] **Step 2:** Verify panel configuration defaults are inert: disabled panels neither activate nor create collectors/listeners, and a request to their path is a 404.
- [ ] **Step 3:** Verify the new model hook stores the supplied collection on `SharpitContext.models` without iterating or introspecting it during install.
- [ ] **Step 4:** Verify `--sharpit-report-only`, `--sharpit-baseline`, and `--sharpit-write-baseline` are accepted by pytest but do not change reports or exit behavior before G1G2 merges.

### Lane-gate refusal contract

Each refusal test builds a temporary git/lane fixture and asserts both nonzero exit and a stable refusal reason. The positive control uses the same fixture with all required evidence and an allowed diff.

- [ ] **Step 1:** `test_lane_gate_refuses_missing_verdict` and `test_lane_gate_refuses_wrong_reviewer_or_sha` cover absent approval, same reviewer id, wrong head SHA, and missing SHA.
- [ ] **Step 2:** `test_lane_gate_refuses_unresolved_finding` covers findings without disposition, fixed without a red-test name, and parked without a reason.
- [ ] **Step 3:** `test_lane_gate_refuses_missing_field_map_handoff_or_checklist` covers each missing required artifact and each missing §6.1 evidence path.
- [ ] **Step 4:** `test_lane_gate_refuses_protected_diff` covers the protected file list one path at a time; `test_lane_gate_refuses_gate_log_for_other_sha` covers stale logs.
- [ ] **Step 5:** `test_lane_gate_accepts_complete_evidence` proves a well-formed lane with matching head-SHA logs is accepted.

## Lane evidence checklist

At completion `.superpowers/sdd/0.4.0/lanes/F/` holds current `handoff.md`; `review.md` with fresh reviewer id distinct from implementer, head SHA and final line `VERDICT: APPROVE`; `findings.md` with each row fixed/red-test or parked/reason; `field-map.md` for every added DTO key or null reason; `checklist.md` mapping applicable §6.1 items to evidence paths; `gate/` logs for lane gate and four gates pinned to head SHA.

## Definition of done

- [ ] Tasks 1–5 complete; suite behavior/counts identical before and after F.
- [ ] Every future panel remains absent until its owner flips `implemented=True`.
- [ ] Lane gate refuses each malformed/protected case and accepts complete evidence.
- [ ] Handoff is current and downstream lanes can consume the infrastructure.
