# E2: a stable identity for a swallowed-exception finding (#66)

> **For agentic workers:** one task at a time; `/sharpit:check` before every commit; `scripts/dev/red_check.py`
> before every `test:` commit.

**Goal:** a `dismissedFindings` entry, a `dismissedRules` fingerprint and a baseline entry for a
`sharpit.swallowed-exception` finding keep matching when unrelated lines move, and a dismissal never moves onto another
clause: when the clause itself changes, the finding comes back.

**Cause:** the identity is `<path>:<line of the except header>:<Type>` (`engine/testsession/gates.py`). The line is in
the dismissal key and, through `Finding.fingerprint`, in the baseline key and the SARIF `sharpitFingerprint/v1`.

**Predict verdict:** CAUTION. The change decides what counts as a dismissed finding, so a wrong match is a silent pass.
The design therefore fails closed: the key is derived from the clause's own content, so only that clause matches it.

## Identity

`<relpath>:<scope qualname>:<Type>#<key>`

- `<relpath>` is the file path relative to the pytest rootdir when under it, otherwise absolute.
- `<scope qualname>` is the qualified name CPython gives the code that holds the clause (`<module>` at module level,
  `Outer.method`, `outer.<locals>.inner`, the bare name of a nested definition declared `global`). Nested definitions
  are their own scopes.
- `<Type>` is the exception class name seen at runtime.
- `<key>` is the first 8 hex digits of the SHA-256 of a canonical text of the clause's `try` body and handler, with no
  positions (the same text on every supported Python version). Byte-identical clauses of one scope are
  indistinguishable by construction, so they get `.<n>/<m>`, their place among the m twins, and adding or deleting a
  twin changes every twin key.

A line added above the `try` or elsewhere in the function keeps the key. Swapping two `try` blocks, or moving a log
call from one clause to another, cannot hand a dismissal over, because each key follows its clause. An edit inside the
`try` body or the handler changes the key, so the finding comes back. Only `ast.Try` clauses count (`except*` stays out,
as for the static advisors). The identity is computed in the worker from the AST that already selected the clause, and
only for the clause the runtime asks about; it travels in the fact JSON and the controller never recomputes it. The
`FASTAPI-ERR-001` violation of the REST API advisor uses the same scope and key as its target. An identity the
dismissal store would refuse (over 512 characters) cannot be written as an entry: the message names the fingerprint to
list under `dismissedRules`, which covers one test only. The earlier line-keyed entries no longer dismiss; they only
produce a report warning naming the key of the clause now on that line.

## Scenarios

| # | Scenario | Expected |
|---|---|---|
| 1 | A line is added above the function | Identity unchanged; the dismissal still matches. |
| 2 | A line is added inside the function, above the handler | Identity unchanged. |
| 3 | The same exception type is swallowed in another function of the file | Different identity; a dismissal for the first does not match. |
| 4 | Property getter and setter with one qualified name | One scope; two different keys, each dismissed separately. |
| 5 | `if`/`else` redefinition of one function | One scope; two different keys. |
| 6 | Handler in a nested function | Own scope `outer.<locals>.inner`. |
| 7 | Handler at module level | Scope `<module>`. |
| 8 | Handler in a class body | Scope is the class qualified name. |
| 9 | Handler in an `async def` | Scope is the function qualified name, as for `def`. |
| 10 | Two `try` blocks swap places | Each key stays with its clause; no dismissal moves. |
| 11 | One clause gains a log call while another loses its log call | The first key matches nothing; the second clause's key is unchanged; no dismissal moves. |
| 12 | A line is added inside the `try` body, or the handler is edited | The key changes; the finding is active. A line added above the `try` keeps the key. |
| 13 | Byte-identical clauses in one scope | Keys `<hash>.<n>/<m>`; adding or deleting a twin changes every twin key; a single clause has no suffix. |
| 14 | `except*` | Not a swallowing clause; the static advisors are unchanged. |
| 15 | A nested definition declared `global` | Its bare qualified name, as the code object has it. |
| 16 | The working directory changes after the rootdir is fixed | The path stays relative to the rootdir. |
| 17 | Legacy `<path>:<line>:<Type>` entry whose line still holds the clause | Dismisses nothing; the report warns naming the key of the clause on that line. |
| 18 | Legacy entry beside its new key | The report warns that the line-keyed entry is stale and to remove it. |
| 19 | Legacy entry in the working-directory path form while pytest runs outside the rootdir | The warning still appears. |
| 20 | Legacy and new keys of one finding | Cannot collide: a legacy key has a numeric second segment. |
| 21 | The same run under `-n 0` and `-n 2` | The same identities and fingerprints. |
| 22 | A baseline and a SARIF file written before a line move | The fingerprint is unchanged; the finding stays `existing`. |
| 23 | First run after the upgrade, with a baseline or a `dismissedRules` fingerprint from the line-keyed form | No match; the finding is `new` and active (fail closed); the changelog names the one-time rewrite. |
| 24 | A fact JSON from the previous form (no identity) | Loads; the gate falls back to the legacy key. |
| 25 | The identity printed in the finding message | Pasted into `sharpit.yml` it dismisses the finding. |
| 26 | An identity over 512 characters | The message says it cannot be dismissed by key and names the fingerprint. |
| 27 | A handler seen at runtime | Its identity is in the static set computed from the source, and its scope is the code object's qualified name. |
| 28 | A line is added above a route handler module's broad handler | The `FASTAPI-ERR-001` target is unchanged. |

## Tasks

### Task 1: Scenario and plan

**Files:** this file.

- [ ] **Step 1:** Commit `docs: scenario and plan for a stable swallowed-exception identity (#66)`.

### Task 2: Tests first

**Files:** `tests/engine/testsession/test_swallowed.py`, `tests/engine/testsession/test_gates.py`,
`tests/engine/restapi/test_swallowed_rule.py`, `tests/pytest_plugin/test_plugin_swallowed.py`.

- [ ] **Step 1:** Write the failing tests for the scenarios. Every input built with `str.replace` asserts that the
      replacement changed the text.
- [ ] **Step 2:** Run `scripts/dev/red_check.py` on every new node id; each red is an assertion naming the defect.
- [ ] **Step 3:** Commit `test: a dismissed swallowed exception stays dismissed when unrelated lines move (#66)`.

### Task 3: The identity in the engine and the worker

**Files:** `src/sharpit/engine/testsession/swallowed.py`, `src/sharpit/engine/testsession/facts.py`,
`src/sharpit/pytest_plugin/swallowed.py`.

- [ ] **Step 1:** `swallowed.py` returns, for a swallowing clause, its line, scope and content key; the static
      listing of the same sites shares the code, and the runtime lookup reads the site from the index.
- [ ] **Step 2:** `SwallowedFact` carries the identity; an older JSON without it loads with no identity.
- [ ] **Step 3:** The worker builds the identity string from the site and the path relative to the rootdir.

### Task 4: Dismissal, message, baseline

**Files:** `src/sharpit/engine/testsession/gates.py`, `src/sharpit/pytest_plugin/session.py`,
`src/sharpit/engine/advisors/findings.py`, `src/sharpit/engine/advisors/dismissals.py`,
`src/sharpit/engine/collectors/restapi/rules.py`.

- [ ] **Step 1:** The gate keys the finding on the fact's identity, also matches the legacy line-keyed pair, and prints
      the identity (or the fingerprint route for an over-long one) in the message.
- [ ] **Step 2:** A legacy match adds a report warning naming the clause it matches, or the redundant entry.
- [ ] **Step 3:** The REST API violation target uses the scope and key; the `Finding.fingerprint` docstring is true.
- [ ] **Step 4:** Commit `fix: a dismissed swallowed exception stays dismissed when unrelated lines move (#66)`.

### Task 5: Documents

**Files:** `CHANGELOG.md`, the pages that document `dismissedFindings` (both copies of the skill), the deviation row
`docs/reference/matrix-updates/e2-66.tsv`.

- [ ] **Step 1:** `CHANGELOG.md` `Unreleased`: the new key; the legacy form still accepted with a warning; one
      `--sharpit-write-baseline` rewrite; `dismissedRules` fingerprints re-dismissed once; swallowed-exception SARIF
      alerts reopen once.
- [ ] **Step 2:** The documentation pages that show a swallowed-exception `dismissedFindings` entry use the new form.
- [ ] **Step 3:** One row: the identity form against BootUI's `AdvisorFindingIdentity`.
- [ ] **Step 4:** Commit `docs: the swallowed-exception identity, its migration and its deviation row (#66)`.

### Task 6: Gates

- [ ] **Step 1:** `uv run pytest -q -n 2` over `tests/engine/testsession`, `tests/engine/advisors`,
      `tests/engine/restapi` and `tests/pytest_plugin`; `ruff check`; `ruff format --check`; `pyright`. The overhead
      budget test for the swallowed-exception callback passes unchanged.
