# E2: a stable identity for a swallowed-exception finding (#66)

> **For agentic workers:** one task at a time; `/sharpit:check` before every commit; `scripts/dev/red_check.py`
> before every `test:` commit.

**Goal:** a `dismissedFindings` entry, a `dismissedRules` fingerprint and a baseline entry for a
`sharpit.swallowed-exception` finding keep matching when unrelated lines move, and stop matching when the handler
itself changes meaning (a swallowing clause added, removed or given a log call in the same scope).

**Cause:** the identity is `<path>:<line of the except header>:<Type>` (`engine/testsession/gates.py`). The line is in
the dismissal key and, through `Finding.fingerprint`, in the baseline key and the SARIF `sharpitFingerprint/v1`.

**Predict verdict:** CAUTION. The change decides what counts as a dismissed finding, so a wrong match is a silent pass.
The design therefore fails closed: any change that could move a dismissal onto another clause makes the key differ, and
the finding comes back.

## Identity

`<relpath>:<scope qualname>:<Type>#<n>/<m>`

- `<relpath>` is the file path as today (relative to the working directory when under it, otherwise absolute).
- `<scope qualname>` is the qualified name of the innermost function or class body that holds the clause, computed
  from the parsed source (`<module>` at module level, `Outer.method`, `outer.<locals>.inner`). Nested definitions are
  their own scopes.
- `<Type>` is the exception class name seen at runtime.
- `<n>/<m>`: `n` is the 1-based source-order position of the clause among the swallowing clauses (broad and silent) of
  that exact scope; `m` is how many there are. Definitions that share a qualified name (an `if`/`else` redefinition, a
  property getter and setter) are one scope.

Adding, removing or logging a swallowing clause in a scope changes `m`, so every key of that scope changes: a dismissal
comes back instead of moving to a neighbouring clause. The identity is computed once, in the worker, from the AST that
already selected the clause, and travels in the fact JSON; the controller never recomputes it.

## Scenarios

| # | Scenario | Expected |
|---|---|---|
| 1 | A line is added above the function | Identity unchanged; the dismissal still matches. |
| 2 | A line is added inside the function, above the handler | Identity unchanged. |
| 3 | The same exception type is swallowed in another function of the file | Different identity; a dismissal for the first does not match. |
| 4 | Property getter and setter with one qualified name | One scope: `#1/2` and `#2/2`, each dismissed separately. |
| 5 | `if`/`else` redefinition of one function | One scope, counted together in source order. |
| 6 | Handler in a nested function | Own scope `outer.<locals>.inner`; not counted in `outer`. |
| 7 | Handler at module level | Scope `<module>`. |
| 8 | Handler in a class body | Scope is the class qualified name. |
| 9 | Handler in an `async def` | Scope is the function qualified name, as for `def`. |
| 10 | A swallowing clause is inserted above a dismissed one | `m` grows; the old key matches neither clause; both findings are active. |
| 11 | The dismissed clause is deleted | The other clause's key changes (`m` shrinks); it is active, not dismissed. |
| 12 | The dismissed clause gains a log call | It stops swallowing and no finding exists; the remaining clause's key changes. |
| 13 | Legacy `<path>:<line>:<Type>` entry whose line still holds the clause | Matches, and the report warns naming the legacy entry and the new key. |
| 14 | Legacy entry after the line moved | Does not match (unchanged behaviour); the finding prints the new key. |
| 15 | Legacy and new keys of one finding | Cannot collide: a legacy key has a numeric second segment, the new one a qualified name and `#n/m`. |
| 16 | The same run under `-n 0` and `-n 2` | The same identities, from the worker facts. |
| 17 | A baseline written before and read after a line move | The fingerprint is unchanged; the finding stays `existing`. |
| 18 | First run after the upgrade, with a baseline or a `dismissedRules` fingerprint from the line-keyed form | No match; the finding is `new` and active (fail closed); the changelog names the one-time rewrite. |
| 19 | A fact JSON from the previous form (no identity) | Loads; the gate falls back to the legacy key. |
| 20 | The identity printed in the finding message | Parses with the dismissal store (at most 512 characters) and dismisses the finding when pasted. |
| 21 | A handler seen at runtime | Its identity (without the type) is in the static set computed from the source. |

## Tasks

### Task 1: Scenario and plan

**Files:** this file.

- [ ] **Step 1:** Commit `docs: scenario and plan for a stable swallowed-exception identity (#66)`.

### Task 2: Tests first

**Files:** `tests/engine/testsession/test_swallowed.py`, `tests/engine/testsession/test_gates.py`,
`tests/engine/testsession/test_baseline.py`, `tests/engine/testsession/test_sarif.py`,
`tests/engine/advisors/test_dismissals.py`, `tests/pytest_plugin/test_plugin_swallowed.py`,
`tests/pytest_plugin/test_plugin_xdist.py`.

- [ ] **Step 1:** Write the failing tests for scenarios 1 to 21. Test 10 is first written against a plain `#n` key to
      show that a clause inserted above a dismissed one would inherit its dismissal; `/m` is added only after that red.
- [ ] **Step 2:** Run `scripts/dev/red_check.py` on every new node id; each red is an assertion naming the defect.
- [ ] **Step 3:** Commit `test: a dismissed swallowed exception stays dismissed when unrelated lines move (#66)`.

### Task 3: The identity in the engine and the worker

**Files:** `src/sharpit/engine/testsession/swallowed.py`, `src/sharpit/engine/testsession/facts.py`,
`src/sharpit/pytest_plugin/swallowed.py`.

- [ ] **Step 1:** `swallowed.py` returns, for a swallowing clause, its line, scope, position and count; the static
      listing of the same sites shares the code.
- [ ] **Step 2:** `SwallowedFact` carries the identity; an older JSON without it loads with no identity.
- [ ] **Step 3:** The worker builds the identity string from the site and the relative path.

### Task 4: Dismissal, message, baseline

**Files:** `src/sharpit/engine/testsession/gates.py`, `src/sharpit/pytest_plugin/session.py`,
`src/sharpit/engine/advisors/findings.py`, `src/sharpit/engine/testsession/sarif.py`.

- [ ] **Step 1:** The gate keys the finding on the fact's identity, also matches the legacy line-keyed pair, and prints
      the identity in the message.
- [ ] **Step 2:** A legacy match adds a report warning naming the entry and its new key.
- [ ] **Step 3:** Correct the `Finding.fingerprint` docstring and the SARIF fingerprint comment; keep
      `sharpitFingerprint/v1`.
- [ ] **Step 4:** Commit `fix: a dismissed swallowed exception stays dismissed when unrelated lines move (#66)`.

### Task 5: Documents

**Files:** `CHANGELOG.md`, the pages that document `dismissedFindings`, `docs/reference/matrix-updates/e2-66.tsv`.

- [ ] **Step 1:** `CHANGELOG.md` `Unreleased`: the new key; the legacy form still accepted with a warning; one
      `--sharpit-write-baseline` rewrite; `dismissedRules` fingerprints re-dismissed once; swallowed-exception SARIF
      alerts reopen once.
- [ ] **Step 2:** The documentation pages that show a swallowed-exception `dismissedFindings` entry use the new form.
- [ ] **Step 3:** One deviation row: the identity form against BootUI's `AdvisorFindingIdentity`.
- [ ] **Step 4:** Commit `docs: the swallowed-exception identity, its migration and its deviation row (#66)`.

### Task 6: Gates

- [ ] **Step 1:** `uv run pytest -q -n 2` over `tests/engine/testsession`, `tests/engine/advisors` and
      `tests/pytest_plugin`; `ruff check`; `ruff format --check`; `pyright`. The overhead budget test for the
      swallowed-exception callback passes unchanged.
