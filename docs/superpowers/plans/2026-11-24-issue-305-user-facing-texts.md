# Issue #305: user-facing texts in the pytest and pentest output

**Goal:** four user-facing texts reported against 0.9.0 read correctly on a Python host. No gate verdict and no
finding fingerprint changes.

**Branch:** `fix/305-user-facing-texts`, from `origin/main`. One pull request, one commit per task.

**Method:** test-driven, one vertical slice per task: the failing test at the named seam, watched red on its assertion
(`scripts/dev/red_check.py`), then the smallest change that makes it pass.

**Revision 2** folds in the plan review: Task 1 covers every Java-stack text a FastAPI scan
shows and the golden fixture that pins one; Task 2 covers every `path:line` source; Task 3 lists all five gates and notes
unattached capture; Task 4 fixes the two other lines on the page that blur the gates.

## Seams under test

| Seam | What it catches | What it misses |
|---|---|---|
| Pentest report DTO, before a scan (`initial_report()`) and after a scan with findings and without | Java-stack wording in a recommendation, coverage note, limitation or `learnMoreUrl` | Strings in the UI bundle |
| `pytester` run of the plugin: the N+1, repeated-statement and unbounded-read finding messages | An absolute path for a site under the rootdir | Sites outside the rootdir, which stay absolute by design (as for swallowed exceptions) |
| `pytester` run of the plugin: the "sharpit checked:" terminal line | A gate missing from the list, or a missing note when swallowed-exception capture did not attach | Whether a gate found evidence, which the line does not claim |
| The docs page text | The stale limitation sentence and the gate names on the page | Other pages |

## Tasks

### Task 1: pentest texts name the Python stack

Texts to adapt (every one a FastAPI scan or the report before a scan can show):

- `src/sharpit/engine/collectors/pentesting/checks.py:125` (the `nosniff` recommendation, "Spring Security headers").
- `checks.py:332,376`: the `learnMoreUrl` of PT-A05-006 and PT-A10-001 points at Spring Boot servlet docs; point it at
  the Starlette/FastAPI error-handling docs.
- `src/sharpit/engine/collectors/pentesting/report.py:118-124` (initial coverage: "Spring MVC mappings", "actuator
  mappings"), `:142` ("BootUI does not send injection payloads"), `:148,150` (A07, "Spring Security wiring"), `:191`
  (the limitation), `:382-389` and `:427-429` (the scanned A01/A02/A07/A08 notes: "BootUI cannot infer", "Actuator
  configuration", "Servlet mappings", "Spring framework evidence"). The scanned branch overwrites the initial A07 note,
  so both are changed together.

Red: one parametrized report test over `initial_report()`, a clean scanned report and a scanned report with findings
(each case first asserts the targeted finding or note exists, so a missing finding cannot pass it) asserts that no
recommendation, coverage note, limitation or `learnMoreUrl` contains, case-insensitively, `spring`, `jvm`, `servlet`,
`actuator` or `bootui`. Coverage statuses stay as they are.

Green: each text adapted (`BootUI` to `sharpit`, Spring Security headers to security-header middleware, Spring MVC or
servlet mappings to the app's routes, the A07 note describing its actual evidence, the Basic or Digest
challenge headers of the synthetic responses (`report.py:298,427`), and stating that dependency-based authentication
is outside A07 coverage). A note describes only the evidence sharpit collects.

Golden fixture: `tests/fixtures/bootui/2.5.0/pentesting/asgi-captured.json:10` is derived by hand for the ASGI
report, not a BootUI capture, so it is updated to the new texts; the separate BootUI contract projection the same test
checks (`tests/engine/collectors/pentesting/test_pentesting_report.py:84-96`) is preserved. Each adapted text, with
its BootUI original, is a deviation row in the 0.10.0 matrix fragment; the fragment is wired into
`scripts/dev/generate_parity_deviations.py` and the generated `PARITY.md` if 0.10.0 has none there yet. Verbatim pins
in `test_pentesting_report.py:20`, `test_pentesting_cors.py:675-680` and
`tests/fastapi/test_pentesting_exposure_incomplete.py:174` move to the new texts.

Out of scope: `engine/collectors/security/rules_config.py` (Spring Security rule titles). Those are rule texts of
another panel; they are a separate finding if they show on a Python host.

### Task 2: every finding location is rootdir-relative

`path:line` sources, all from `co_filename`: `_first_application_location` and `_declaration_line` in
`src/sharpit/engine/sqla/orm.py:62,89,97` (relationship sites, the "declared at" fallback, statement sites) and the
unbounded-read location (`orm.py:365`); printed in `src/sharpit/engine/testsession/gates.py:173,212`.

Red: `pytester` runs with the site in a test file under the rootdir, one per message: a direct lazy load, the
declaration fallback, a repeated statement, an unbounded read. Each asserts the full location (`test_x.py:<line>`),
no drive letter and no leading `/`. The facts serialization test asserts the same for `relationshipSites` and
`statementSites`.

Green:

- `_relative` moves from `src/sharpit/pytest_plugin/swallowed.py:40` to a public helper in the pytest plugin
  (`pytest_plugin/paths.py`, `relative_location`), used by both captures.
- After `sqla.apply_relationship_facts(test)` (`pytest_plugin/session.py:85`) and the unbounded-read facts
  (`session.py:86`), the plugin rewrites the filename part of each location. The line is split from the right
  (`rsplit(":", 1)`, since a Windows drive has its own colon), a fallback prefix ("outside application code",
  "declared at") is kept, and `None` stays `None`. Outside the rootdir or on another drive the path stays absolute.
- The engine keeps recording the absolute `co_filename`: it has no rootdir, and the relative form belongs to the
  pytest adapter.

Checked: finding fingerprints hash the identity or target, never the message or location
(`engine/advisors/findings.py:35`), so existing baselines stay valid. `relationshipSites` and `statementSites` are serialized
worker facts (`engine/testsession/facts.py:221,224`), not part of the public report, which carries only the derived
messages (`engine/testsession/report.py:51`); the serialization assertion stays at that worker boundary, and the
changelog names only the changed messages.

### Task 3: the "sharpit checked" line lists the gates that ran

File: `src/sharpit/pytest_plugin/terminal.py:131`.

The line names the gates the plugin evaluated, which are all five test-runtime gates: `sharpit.max-queries`,
`sharpit.n-plus-one`, `sharpit.exception`, `sharpit.swallowed-exception`, `sharpit.unbounded-read`. The names come
from one tuple in `engine/testsession/gates.py`, not a second hand-written list. Whether a gate found evidence is not
claimed by this line, and no new coverage tracking is added; a gate's verdict is unchanged.

One exception: when swallowed-exception capture did not attach on a process of the run (`CaptureStatus.attached`,
`pytest_plugin/swallowed.py:75`; under xdist the workers' per-worker source facts count, because the controller
collects nothing, `pytest_plugin/session.py:113`), the line appends `sharpit.swallowed-exception not attached on
<n> of <m> processes: <reason>`. The merged `sources` entry (`engine/testsession/outcome.py:96`) cannot tell partial
from total failure, so the note reads the per-worker facts.

Red: `pytester` runs asserting the line (a) names all five gates, including `sharpit.swallowed-exception` when that
gate fired; (b) carries the note `1 of 1` when capture is forced unavailable through the existing capture-failure test
seam; (c) under `-n 2`, names all five gates without the note when both workers attached, with `1 of 2` when one
worker's capture is forced unavailable, and `2 of 2` when both are.

### Task 4: the docs page states what each gate detects

File: `website/docs/pytest-plugin.md:17,65,251`.

- Line 251: the sentence that silent `try...except` blocks cannot be detected is replaced. `sharpit.exception` tracks
  emitted log records that carry `exc_info` and exceptions handled by registered exception handlers; `sharpit.swallowed-exception`
  tracks broad handlers that swallow an exception during a test's call phase, when capture is attached. The remaining
  limits are named: narrow handlers, the setup and teardown phases, and `except*`.
- Lines 17 and 65 call `sharpit.exception` "Swallowed exceptions"; they name each gate by what it checks. The gates
  table (`pytest-plugin.md:59-65`) and the captured output in `website/docs/tutorial.md:387` list all five gates and
  match the Task 3 line.
- If `tests/docs` has a page-text check, it asserts the old sentence is absent; otherwise this task is docs-only.

## Verification

- `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`.
- `uv run pytest -q -n 4 tests/pytest_plugin tests/engine/collectors/pentesting tests/engine/testsession tests/docs`
  (not the full suite locally; CI runs it).
- The PR lists each `finding → test → red output`.
