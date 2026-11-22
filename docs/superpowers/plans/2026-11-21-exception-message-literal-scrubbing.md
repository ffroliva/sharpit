# Exception-message literal scrubbing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port BootUI v2.5.0 `MessageExposure.scrubBindingLiterals` so recognized user-input literals are scrubbed from projected exception and cause messages outside FULL.

**Architecture:** Keep the implementation in framework-free masking code and call it at shared output projection boundaries, including exception REST/request-profile, MCP/CLI projections and pytest sink/report paths. This is projection-time work to avoid capture hot-path overhead; do not mutate host exceptions or duplicate A4a structured binding-diagnostic extraction.

**Tech Stack:** Python 3.12–3.14, standard-library regular expressions, pytest, existing `Masker`, masking corpus gate.

---

## Global Constraints

- Python `>=3.12`; runtime dependencies exactly `starlette` and `packaging`. `fastapi` and `pydantic-settings` are optional: import them only inside `try/except ImportError` or in `sharpit/fastapi/`.
- Every contract DTO key is emitted (nulls included), camelCase, no envelope, epoch ms. Error bodies and reason strings are verbatim from the contract §1/§10 with `BootUI`→`sharpit`.
- **Reads have no side effects:** no GET route and no read MCP or CLI tool of the console installed in a host application may open a socket, write a file, change a logger level or change `os.environ`.
- **Secrets masked** before filtering and before any output (JSON, errors, MCP, CLI). `FULL` exposure warns.
- No module under `src/` over 1000 lines; complexity ratchets only go down.
- **Port BootUI, do not reinvent:** read pinned v2.5.0 source/tests before code; same replacements and ordering where applicable; each ported test cites its BootUI source with `# ported:`. Every Python/runtime adaptation gets a row in `docs/reference/matrix-updates/0.8.0-a4b.tsv`.
- Safety model 1–6 and architecture rules 1–6 never regress. No unrelated production behavior or A4a diagnostics/422 wiring in this lane.
- Tests use pytest-xdist `-n` (at most `-n 4`); only touched modules and neighbours. Do not run the whole suite. Run long commands detached with a log. Before every `test:` commit run `uv run python scripts/dev/red_check.py <node ids>`.
- Commit each task with a conventional prefix, explicit paths and `git commit -s`; no AI attribution. Do not push, open PRs, merge, rebase, stash or force anything.

## Risk register

| Severity | Risk | Mitigation |
|---|---|---|
| Critical | A recognized input literal survives in an exception or cause output | Direct assertions at every output surface and each exception-chain form; one mutation per pattern must fail a named test |
| Critical | Scrubber alters benign diagnostics or regresses existing masking corpus rows | Paired false-positive controls and base-vs-branch differential for every surface and exposure mode |
| High | Regex runtime grows with attacker-controlled message size | Anchor known grammars, keep captures bounded by the existing message cap, and add huge-input elapsed-time test |
| High | Pytest fallback bypasses the normal text path | Exercise empty/MASK fallback and assert JSON, JUnit and SARIF output directly |
| High | Capture overhead changes | Scrub at projection time; do not change capture recording or its budgets |
| High | A4b duplicates A4a structured binding diagnostics | Keep changes to free-form strings only; test structured diagnostics remain under A4a policy |

## File and interface map

- `src/sharpit/engine/masking.py`: one shared pure text scrubber adjacent to existing text masking; no optional imports.
- `src/sharpit/engine/capture/exceptions.py`: apply scrub while producing `report`, `detail`, and `request_occurrences` output; stored values remain unchanged.
- `src/sharpit/engine/tools.py`, `src/sharpit/fastapi/routes/__init__.py`, and any projection helpers discovered in implementation: ensure MCP/CLI/REST do not expose an unsanitized copy. Reuse the shared scrubber, no parallel pattern sets.
- `src/sharpit/engine/testsession/sink.py`: apply the shared helper to captured free-form text, including the empty/MASK fallback.
- `tests/engine/test_masking.py`, `tests/engine/capture/test_exceptions.py`, `tests/engine/testsession/test_report.py`, `tests/engine/testsession/test_sarif.py`, `tests/pytest_plugin/`, and `tests/test_masking_corpus.py`: direct assertions for each changed projection and corpus rows. Add only files needed by demonstrated projection paths.
- `docs/reference/matrix-updates/0.8.0-a4b.tsv`: Python grammar, ordering and exposure-policy deviations.

## BootUI contract and chosen adaptations

At v2.5.0 `MessageExposure.scrubBindingLiterals` performs its named structural replacements in a fixed sequence. `ExceptionsService.displayMessage` first applies the exposure policy, returns on null/FULL, and scrubs only the resulting masked text. Preserve BootUI’s mask-then-scrub order for existing BootUI-shaped patterns. Add Python-specific patterns only for observed CPython 3.12–3.14 and supported Pydantic v2 emitted forms; never blanket-replace arbitrary quoted values or brackets. Keep replacement text `******`, Jackson source text `REDACTED`, and identifier-associated bracket form `[*]` where the corresponding structural grammar applies.

Sharpit applies literal scrubbing outside FULL even when `mask_secrets=false`, per the plan’s A4b bullet and safety model 3; this is an explicit safety adaptation from BootUI’s policy-bound scrub. Test order with overlapping secret-shaped values and require every existing gate-corpus row to remain byte-identical apart from rows containing recognized binding literals. If projection-time work cannot cover a sink without changing capture behavior, revise scope only with evidence and retain the capture budget comparison required by the coordinator.

Do not claim arbitrary `RuntimeError("plain literal")` messages are scrubbed. Do not extract or serialize pydantic `msg`, `ctx`, or `input` as structured diagnostics; A4a owns that boundary. Scrub only free-form strings already exposed by sharpit.

## Task 1: Pin emitted grammars and scrubber behavior with direct tests

**Files:**
- Test: `tests/engine/test_masking.py` (or existing masking test module if layout has changed)
- Test: `tests/engine/capture/test_exceptions.py`
- Test: `tests/test_masking_corpus.py`

**Interfaces:** Tests specify the contract for `Masker`-adjacent scrub function and exception projections; no production API is added in this task.

- [ ] **Step 1:** Probe actual exception strings on Python 3.12, 3.13 and 3.14 plus supported Pydantic v2. Record exact observed text in parametrized test fixtures; no guessed forms. Include `int`, `float`, `strptime`, `fromisoformat`, Enum, UUID, Decimal, complex, JSONDecodeError and pydantic `input_value`/custom message/context.
- [ ] **Step 2:** Add failing direct tests named `test_scrubs_int_binding_literal`, `test_scrubs_supported_python_binding_messages`, `test_scrubs_pydantic_rendered_message_only`, `test_preserves_arbitrary_runtime_error_message`, and `test_preserves_binding_message_near_misses`. Use one condition per assertion and cite `# ported: ExceptionsServiceTests.scrubsBoundaryMapKeysAndAdversarialFrameworkMessagesInMaskedMode` for the copied BootUI contract case.
- [ ] **Step 3:** Add failing tests for replacement vocabulary and known BootUI-shaped input examples from `MessageExposureTests`; cite the exact existing BootUI method name after inspecting its source. Preserve no-value and benign controls byte-for-byte.
- [ ] **Step 4:** Run only the named nodes with `uv run pytest -q -n 4 ...`; verify the red output is the missing scrub assertion, not collection/import failure.
- [ ] **Step 5:** Run `uv run python scripts/dev/red_check.py <the exact node ids>` before committing the test-only change. Commit as `test: pin binding literal message grammars` with `git add <explicit test paths>` and `git commit -s`.

## Task 2: Port one bounded shared scrubber

**Files:**
- Modify: `src/sharpit/engine/masking.py`
- Test: direct masking tests from Task 1

**Interfaces:** Provide a single pure helper taking `str | None` and returning `str | None`; no configuration, pydantic import, storage, or I/O.

- [ ] **Step 1:** For each grammar introduced, keep one named replacement branch/pattern with an adjacent test name that fails if that branch is deleted. Use BootUI’s order and replacement vocabulary for corresponding Java forms; add only observed Python patterns.
- [ ] **Step 2:** Implement only those replacements. Each pattern must be tied to its known error grammar; leave arbitrary `RuntimeError` text, ordinary quoted prose, paths and unattached brackets unchanged.
- [ ] **Step 3:** Run Task 1 test nodes and confirm every input literal is absent while benign controls remain byte-identical.
- [ ] **Step 4:** Mutation-check one pattern at a time by deleting it temporarily, run its named test to the raw-literal assertion failure, restore it, and repeat for every pattern. Do not commit mutations.
- [ ] **Step 5:** Commit implementation with `git add src/sharpit/engine/masking.py tests/...` and `git commit -s -m "fix: port bounded binding literal scrubbing"`.

## Task 3: Scrub stored exception messages at all exception projections

**Files:**
- Modify: `src/sharpit/engine/capture/exceptions.py`
- Test: `tests/engine/capture/test_exceptions.py`, relevant FastAPI route tests

**Interfaces:** `ExceptionStore.report`, `detail`, and `request_occurrences` return scrubbed free-form message/cause strings without changing stored capture data, DTO keys or A4a diagnostic fields.

- [ ] **Step 1:** Add failing tests `test_scrubs_each_exception_group_and_cause_message`, `test_exception_message_exposure_modes`, and `test_exception_messages_are_scrubbed_on_rest_projections`. Cover cause and unsuppressed context, nested/multiple ExceptionGroup leaves, and request profile.
- [ ] **Step 2:** Add assertions that `__notes__`, non-string args/repr and A4a structured diagnostics are not newly incorporated into projected message text.
- [ ] **Step 3:** Implement at the shared projection methods; apply the same helper to each free-form group, occurrence and cause message, after existing mask policy. Return `None` unchanged. Keep FULL and METADATA_ONLY behavior exactly as today.
- [ ] **Step 4:** Run `uv run pytest -q -n 4 tests/engine/capture/test_exceptions.py tests/fastapi/<relevant route test>` and confirm all new assertions and neighbours pass.
- [ ] **Step 5:** Commit as `fix: scrub exception projection messages` with explicit paths and `-s`.

## Task 4: Cover MCP and CLI projection parity

**Files:**
- Modify only if a projection bypass is demonstrated: `src/sharpit/engine/tools.py`, `src/sharpit/cli/`, or the corresponding REST route adapter
- Test: `tests/engine/tools/`, `tests/cli/`, and/or `tests/fastapi/` existing projection tests

**Interfaces:** Existing exception DTO and tool schemas remain unchanged; message values follow the shared helper and existing caps.

- [ ] **Step 1:** Add `test_exception_messages_are_scrubbed_on_mcp_and_cli`, issuing actual tool/API requests and asserting sentinels absent from response JSON for MASKED and FULL.
- [ ] **Step 2:** Run those tests against current branch; require failure on a response assertion if a surface bypass exists. If all surfaces already consume Task 3 projection methods, do not add production code; retain the direct passing coverage in this task.
- [ ] **Step 3:** Make the smallest caller change only for a proven bypass, reusing the shared helper. Keep tool names, envelopes, caps and action/read behavior unchanged.
- [ ] **Step 4:** Run the touched MCP/CLI/FastAPI test files with `-n 4` and commit any production/test delta using explicit paths and `git commit -s`.

## Task 5: Scrub pytest sink fallback and output exporters

**Files:**
- Modify: `src/sharpit/engine/testsession/sink.py`
- Test: `tests/engine/testsession/test_report.py`, `tests/engine/testsession/test_sarif.py`, `tests/pytest_plugin/test_plugin_reports.py`

**Interfaces:** Test-session exception group messages and generated JSON/JUnit/SARIF contain scrubbed free-form strings, including when normal `error_text` returns empty or `MASK` and the sink uses its fallback.

- [ ] **Step 1:** Add failing `test_pytest_exception_fallback_and_exporters_scrub_messages` coverage with a sentinel in main, cause and fallback exception output; assert each report format independently.
- [ ] **Step 2:** Add failing `test_exception_message_projection_has_no_side_effects` using the existing no-side-effects fixture for the read/export path where applicable.
- [ ] **Step 3:** Apply the shared scrubber at the sink’s report-output projection; ensure fallback `str(exc)` is passed through the same helper and preserve failure-safe `<unprintable ...>` behavior.
- [ ] **Step 4:** Run touched test-session and plugin files with `uv run pytest -q -n 4 ...`; check JSON, XML and SARIF parse and contain no sentinel.
- [ ] **Step 5:** Commit as `fix: scrub pytest exception report messages` with explicit paths and `-s`.

## Task 6: Expand corpus, differential and merge gates

**Files:**
- Modify: `tests/test_masking_corpus.py` and its existing fixture/data files
- Modify: `docs/reference/matrix-updates/0.8.0-a4b.tsv`
- Review: `scripts/dev/masking_gate.py` and existing outputs; do not weaken gate code

**Interfaces:** A reviewed machine-readable base/branch corpus diff covers direct real requests and every changed output surface/exposure mode.

- [ ] **Step 1:** Add corpus rows for all exact observed grammars, causes/groups, pydantic output, overlapping secret-shaped values, unicode/quotes/newlines, benign near-misses, `mask_secrets=false`, and MASKED/METADATA_ONLY/FULL. Preserve ordinary arbitrary RuntimeError literals as controls.
- [ ] **Step 2:** Add one deviation row per Python grammar and the outside-FULL policy, citing the A4b bullet in `docs/superpowers/plans/2026-11-20-sharpit-0.8.0/PLAN.md`; record mask/scrub order as BootUI parity unless measured output forces the nominated safety deviation.
- [ ] **Step 3:** Run `scripts/dev/masking_gate.py` against `origin/release/0.8.0` and this branch for each required exposure level and listed surface; exercise actual requests, retain revisions and JSONL, and review each row. Require byte-identical existing rows except rows containing recognized binding literals and intentional FULL behavior.
- [ ] **Step 4:** Run only changed modules and neighbours with `uv run pytest -q -n 4 ... tests/parity`; run all tests of each touched module. Record test counts and red outputs from every regression assertion.
- [ ] **Step 5:** Run the repository gates required for this lane: `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`, Sonar new-code coverage at least 85%, cognitive complexity with `uvx --with flake8-cognitive-complexity flake8 --select CCR001 --max-cognitive-complexity 15`, and C901 at most 10. Do not raise a baseline or skip tests.
- [ ] **Step 6:** Commit corpus and deviation updates with explicit paths and `git commit -s -m "test: pin exception message masking parity"`.

## Definition of done

- [ ] All six tasks complete with one signed-off conventional commit per atomic task; no `src/` changes occur until execution begins.
- [ ] Every Critical/High scenario has a named direct test; each scrub pattern is proven by a one-pattern mutation; huge-input test passes its bound.
- [ ] MASKED scrubs supported binding literals even with `mask_secrets=false`; METADATA_ONLY omits; FULL remains byte-for-byte verbatim.
- [ ] Arbitrary plain literals in RuntimeError prose are not claimed as covered; A4a diagnostics and 422 wiring remain untouched.
- [ ] Base/branch masking differential and real-request review pass on all surfaces and modes; existing corpus rows remain byte-identical apart from named binding-literal rows.
- [ ] `tests/parity`, touched-module tests, lint, format, pyright, Sonar coverage, cognitive complexity and C901 gates pass.
- [ ] Each ported test includes `# ported:`; all adaptations are recorded in the lane TSV.
- [ ] `/sharpit:live-verify` is not required because no endpoint behavior or UI code is added beyond existing DTO message projection; direct request integration coverage is required.

## Next step

Plan written. Next: `/sharpit:status --feature exception-message-literal-scrubbing`, then execute task by task with `superpowers:subagent-driven-development`.
