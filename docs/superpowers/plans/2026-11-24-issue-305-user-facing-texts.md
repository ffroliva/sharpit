# Issue #305: user-facing texts in the pytest and pentest output

**Goal:** four user-facing texts reported against 0.9.0 read correctly on a Python host. No gate verdict changes.

**Branch:** `fix/305-user-facing-texts`, from `origin/main`. One pull request, one commit per task.

**Method:** test-driven, one vertical slice per task: the failing test at the named seam, watched red on its assertion
(`scripts/dev/red_check.py`), then the smallest change that makes it pass.

## Seams under test

| Seam | What it catches | What it misses |
|---|---|---|
| Pentest report DTO (`PentestingService` report, the texts the panel, MCP and CLI show) | Java-stack wording in a recommendation, coverage note or limitation | Wording in the UI's own static strings |
| `pytester` run of the plugin, the N+1 finding's `message` | An absolute path in "first lazy load at ..." when the call site is under the rootdir | Sites outside the rootdir, which stay absolute by design (as for swallowed exceptions) |
| `pytester` run of the plugin, the "sharpit checked:" terminal line | A gate that fired but is missing from the line | Gates that never fire in the run |
| `tests/docs` text checks (or a new assertion there) | The stale limitation sentence returning | Other prose in the page |

## Tasks

### Task 1: pentest texts name the Python stack

Files: `src/sharpit/engine/collectors/pentesting/checks.py:125`, `src/sharpit/engine/collectors/pentesting/report.py:142,150,191`.

- Red: a report test asserts that no recommendation, coverage note or limitation contains `Spring`, `JVM`, `servlet`,
  `Actuator` or `BootUI`.
- Green: the BootUI texts adapted, as contract texts are adapted elsewhere (`BootUI` → `sharpit`, Spring Security
  headers → security-header middleware, the A07 row names the FastAPI/Starlette security dependencies, the limitation
  names what has no Python equivalent without the Java terms). Each changed text is a deviation row in the 0.10.0
  matrix fragment, with the BootUI original.
- Out of scope: `engine/collectors/security/rules_config.py` (Spring Security rule titles). Those are rule texts, not
  pentest texts; they are a separate finding if they show on a Python host.

### Task 2: the N+1 finding reports a rootdir-relative path

Files: `src/sharpit/pytest_plugin/session.py:85` (caller of `sqla.apply_relationship_facts`),
`src/sharpit/pytest_plugin/swallowed.py:40` (`_relative`).

- Red: a `pytester` run with an N+1 in a test file under the rootdir asserts the finding message contains
  `first lazy load at test_x.py:<line>` and no drive or leading `/`.
- Green: the plugin rewrites `phase.relationship_sites` and the location in `phase.statement_sites` to the rootdir
  relative form after `apply_relationship_facts`, with the same `_relative` the swallowed-exception capture uses
  (outside the rootdir or on another drive stays absolute). The engine (`engine/sqla/orm.py`) keeps recording the
  absolute `co_filename`: it has no rootdir, and the relative form belongs to the pytest adapter.
- Check: baseline fingerprints do not include the site (confirm in `gates.py`), so existing baselines stay valid.

### Task 3: the "sharpit checked" line lists the gates that ran

File: `src/sharpit/pytest_plugin/terminal.py:131`.

- Red: a `pytester` run where `sharpit.swallowed-exception` fires asserts the line names `sharpit.swallowed-exception`.
- Green: the gate list names every test-runtime gate (`MAX_QUERIES`, `N_PLUS_ONE`, `EXCEPTION`, `SWALLOWED`,
  `UNBOUNDED_READ`), each only when it was enabled for the run, from one tuple in `engine/testsession/gates.py`
  rather than a second hand-written list.

### Task 4: the stale limitation sentence

File: `website/docs/pytest-plugin.md:251`.

- The sentence is replaced: logged and handler-reported exceptions are tracked by `sharpit.exception`; silent
  `try...except` blocks by `sharpit.swallowed-exception` (when capture is attached, Python 3.12+ `sys.monitoring`).
  The remaining limitation is stated precisely (what capture cannot see).
- A docs test asserts the old sentence is absent, if `tests/docs` has a page-text check to extend; otherwise this task
  is docs-only and needs no test.

## Verification

- `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`.
- `uv run pytest -q -n 4 tests/pytest_plugin tests/engine/collectors/pentesting tests/docs` (not the full suite
  locally; CI runs it).
- The PR lists each `finding → test → red output`.
