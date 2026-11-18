# W0: pin BootUI 2.4.0

> **For agentic workers:** one task at a time; `/sharpit:check` before every commit; `scripts/dev/red_check.py`
> before every `test:` commit. Read the named BootUI files at `v2.4.0` in a BootUI clone; never from a summary.

**Goal:** the parity tests, status files and docs measure sharpit against BootUI 2.4.0 instead of 2.3.0, with no change
to sharpit's behaviour, and CI stays green.

**Architecture:** the 2.4.0 fixture tree is captured with the 2.3.0 pipeline, changing only its pins. Each 2.3.0
parity test is retargeted to 2.4.0, not copied: a release pins one BootUI version, and the 2.3.0 fixtures stay in the
repository as history. Every difference between the two fixture trees is either already in the expected list below or
is reported as a finding. Every behaviour difference between sharpit and 2.4.0 is recorded as a `partial` or `missing`
row in a status file; those rows are the Track A and B backlog, and each later lane removes its own rows.

**Predict verdict:** not required (no behaviour change; no safety-model or architecture-rule text changes meaning).

## Expected fixture delta (2.3.0 → 2.4.0)

Any difference outside this table is a finding and goes into `docs/reference/BOOTUI-2.4.0-DELTA.md` (Task 3).

| File | Expected | BootUI source |
|---|---|---|
| `meta.json` | `bootuiVersion: 2.4.0`, new `commit`, `tag`, `tagObject`, `captured`; same `app` and `profile` | pin |
| `ids.json`, `routes.json`, `properties.json`, `panels.json` | identical | `BootUiPanels.java`, `BootUiProperties.java` unchanged |
| `tools.json` | seven description or summary strings differ; every `name`, `schema`, `panel`, `action`, `stacks` equal | `bootui-tools.json` (+7/−7) |
| `rule-ids.json` | adds `SEC-STATIC-001` | `E/engine/staticsecurity/StaticSecurityAnalysisRule.java` |
| `bootui-tests.json` | regenerated; new test classes and methods | test inventory |
| `exceptions/caught.captured.json` | adds `insufficient` and `partial` | `E/core/dto/CaughtExceptionsReport.java:27-28` |
| `transactions/captured.json`, `transactions/enums.raw.json` | `propagation` values `NEW`/`REQUIRES_NEW`/`NESTED`/`UNKNOWN` where the app has nested boundaries | `E/engine/transactions/TransactionBoundary.java` |
| `security/captured.json`, `security/scanned.captured.json` | the `SEC-STATIC-001` result when the capture app declares no analyzer | `StaticSecurityAnalysisDetector.java` |
| `database-advisor/scanned.captured.json` | possible new WARNING diagnostics, depending on the capture database | `SchemaIntrospector.java:253-272` |
| `cli/captured.json`, `mcp-server/captured.json` | recaptured; same tool list | no tool delta |
| every other panel | same shape | no DTO change in the diff |

## Tasks

### Task 1: Capture and sanitizer pins

**Files:** `scripts/capture_bootui_24.py` (new), `scripts/sanitize_golden.py`, `tests/golden.py`,
`tests/test_bootui_fixtures.py`.
**Produces:** a capture script pinned to `v2.4.0`, and a sanitizer and golden loader that accept the `2.4.0` nested
layout.

- [ ] **Step 1:** Write the failing tests: `sanitize_golden.py` picks the nested layout for a source folder named
      `2.4.0` (expected failure: it picks flat; the docstring names only `2.2.0` and `2.3.0`), and
      `tests/golden.py` applies the 2.3.0 rules (catalog fields, non-empty list) to `fixture_version="2.4.0"`.
- [ ] **Step 2:** Generalise the nested-layout and 2.3.0-rules checks to "2.3.0 or later"; add `META_2_4_0`.
- [ ] **Step 3:** Copy `scripts/capture_bootui_23.py` to `capture_bootui_24.py`, changing only `PINNED_TAG = "v2.4.0"`,
      `PINNED_COMMIT = "0df7ed764688d04f83c246c9965e90158c1db488"`, the output directory, the temporary-directory
      prefix and `bootuiVersion`. Re-check each `defaultValueSource` line citation against `v2.4.0`
      (`BootUiProperties.java` is unchanged, so they should hold).
- [ ] **Step 4:** Commit `test: the golden pipeline accepts the BootUI 2.4.0 nested layout`, then
      `chore: capture script pinned to BootUI 2.4.0`.

### Task 2: Capture the 2.4.0 fixtures

**Files:** `tests/fixtures/bootui/2.4.0/**`.
**Consumes:** Task 1; the `tiny-ledger` capture app built against BootUI 2.4.0, `full` profile.

- [ ] **Step 1:** Build BootUI 2.4.0 with `capture_bootui_24.py`; run the capture app with BootUI 2.4.0; run
      `capture_bootui_live.py` with the unchanged `POST_ALLOW_LIST`; sanitize into `tests/fixtures/bootui/2.4.0/`.
- [ ] **Step 2:** Run `tests/test_bootui_fixtures.py` on the new tree (secrets check, no error bodies, `meta.json`
      complete). Compare the `uncaptured` map in `meta.json` with 2.3.0's; a newly uncaptured route is a finding.
- [ ] **Step 3:** Commit `test: BootUI 2.4.0 live goldens`.

### Task 3: Fixture delta report

**Files:** `docs/reference/BOOTUI-2.4.0-DELTA.md` (new).

- [ ] **Step 1:** Diff `tests/fixtures/bootui/2.3.0` against `2.4.0` file by file. Check each difference against the
      expected table above, and write the report: what matched the expectation, and every unexpected difference with
      its BootUI source and the lane it goes to.
- [ ] **Step 2:** Commit `docs: BootUI 2.3.0 to 2.4.0 fixture delta`.

### Task 4: Retarget the parity tests

**Files:** `tests/parity/test_{routes,properties,tools,rules_architecture,rules_rapi,rules_security}_23.py` →
`_24.py`; `tests/parity/{routes,properties}_23_status.json` → `_24_status.json`; `tests/test_bootui_goldens_23.py` →
`_24.py`; the three tests that pass `fixture_version="2.3.0"`.

- [ ] **Step 1:** Move each file with `git mv` and switch its fixture path to `2.4.0`, one commit per file, so each move
      shows as a rename. Run each file alone (`-n auto`).
- [ ] **Step 2:** For every newly failing case, read the 2.4.0 source and record the difference in the status file
      as `partial` (a known gap, with the lane that closes it: A1 for the tool descriptions and counters, A2 for
      `propagation`, A3 for `SEC-STATIC-001`, A4 for database-advisor diagnostics). A failure that matches no expected
      delta stops the task and goes to the delta report.
- [ ] **Step 3:** Add a ratchet test: the count of `matched` rows in each `_24_status.json` is pinned, and a lane may
      only raise it. Seen red by lowering the pin by one.
- [ ] **Step 4:** Commit `test: parity tests measure against BootUI 2.4.0`.

### Task 5: Version pin in the docs

**Files:** `AGENTS.md`, `ROADMAP.md`, `README.md`, `tests/docs/test_parity_matrix.py`, `docs/reference/PARITY.md`.

- [ ] **Step 1:** `test_parity_matrix.py` recomputes the BootUI and sharpit columns from the 2.4.0 fixtures and
      status files; it fails until `ROADMAP.md` and `README.md` show the 2.4.0 numbers (the routes row is "not
      captured" for 2.4.0 today).
- [ ] **Step 2:** Update `ROADMAP.md` and `README.md`. In `AGENTS.md`, "exactly where BootUI 2.3.0 has the same
      action" becomes 2.4.0: 2.4.0 adds no route and no action, so the set of permitted actions does not change.
- [ ] **Step 3:** Commit `docs: sharpit 0.7.0 measures against BootUI 2.4.0`.

### Task 6: Matrix fragment

**Files:** `docs/reference/matrix-updates/w0-pin-24.tsv`.

- [ ] **Step 1:** One row per status-file difference opened in Task 4, naming its lane.
- [ ] **Step 2:** Commit `docs: 0.7.0 pin-wave matrix fragment`.

## Definition of done

- [ ] All steps checked; CI green on the full matrix.
- [ ] Every 2.3.0 → 2.4.0 fixture difference is expected or reported in `BOOTUI-2.4.0-DELTA.md`.
- [ ] No file under `src/` changed (`git diff --stat origin/main -- src` is empty).
- [ ] Every `partial` row opened by this wave names the lane that closes it.
