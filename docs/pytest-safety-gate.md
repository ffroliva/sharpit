# The safety gate

`pytest --sharpit` runs sharpit's test-session gates and the REST API advisor. The run fails when a finding meets the
configured severity threshold (`--sharpit-fail-on`, default `HIGH`), or when sharpit cannot establish that the run was
fully observed. INFO findings and dismissed findings do not fail. With a baseline, existing findings do not fail; new
findings do.

Sharpit fails closed on unknown results. An incomplete capture, unreadable or malformed baseline, or other unknown
reason exits non-zero by default. `--sharpit-allow-unknown` permits unknown results, but does not permit findings that
meet the gate.

An advisor that read the routes it could and met one opaque mounted sub-app (`Mounted application at /x has no
inspectable routes.`) is reported as `PARTIAL`. It does not make the run `unknown`: the gate passes with a warning
that names what was not read and says that having no finding at or above `--sharpit-fail-on` is not proof there is
none, and a finding at or above the threshold still fails. Everything else stays `UNKNOWN`: an advisor with no usable
routes and a limitation, a router or exception handler sharpit could not read, an errored scan or a rule that threw.
An app with no routes and no limitation is confirmed empty and passes, as it has since 0.3.0. These cases of lost
capture stay `unknown` whatever the advisors report: no SQL source, a missing worker, a hook of the
pytest plugin or of its session sink that fails before the report is written (the report lists the `pytest-plugin` source as not attached, for the worker or the `controller`), and
capture ended before the session did, as a nested in-process pytest run (`pytest.main`,
`pytester.runpytest_inprocess`) does; start such a run with `-p no:sharpit` or in a subprocess. A failed hook in one
attempt of a rerun test keeps the run `unknown`, also when a later attempt is clean. A partly assessed
advisor does not count as having run for baselines: its baselined entries are neither reported fixed nor dropped.

A statement that has no text (`None`, `b""`, a number or a query object passed to a cursor class, to SQLAlchemy's
`exec_driver_sql` or to the stdlib `sqlite3` driver, which refuses it) is counted once with empty text. It does not
make the run `unknown`. Its empty text has no shape, so the N+1 rule does not check it: a repeated statement sent as
query objects counts toward the query total only.

Pytest's exit status is preserved when pytest already returns non-zero. Sharpit changes a successful pytest exit (`0`)
to `1` when the gate fails; it does not replace pytest's status for failing tests, interruption, an internal error, a
usage error or no collected tests. Report-only mode (`--sharpit-report-only`) still writes the report and displays
which findings would fail, but findings do not change pytest's exit status. Unknown results still fail unless
`--sharpit-allow-unknown` is set.

| Result | Exit status |
|---|---:|
| Pytest succeeds and the sharpit gate passes | `0` |
| Pytest succeeds and a finding or disallowed unknown fails the gate | `1` |
| Pytest already has a non-zero status | Pytest's status is preserved |
| Report-only with findings and no disallowed unknown | Pytest's status |

To adopt the gate on a suite with existing findings, first run report-only and review the report. Then create and commit
a baseline after a complete, known run:

```bash
pytest --sharpit --sharpit-write-baseline=sharpit-baseline.json
```

Use that file in CI:

```bash
pytest --sharpit --sharpit-baseline=sharpit-baseline.json
```

Existing findings are recorded as `existing`; newly detected findings are `new` and can fail the gate. A missing,
malformed or unreadable baseline is unknown and fails closed. Baseline writing is refused for partial or unknown runs.
Protect the baseline in code review so a change cannot silently accept its own findings.

A baselined test-runtime finding that is no longer seen counts as `fixed` only when the run proves it: its test ran,
every call phase of its deciding attempt passed, the run's evidence was whole, and no attempt or phase of the test still
shows the finding once every gate is evaluated without relaxation. Each baseline entry records `owner`, a 16-hex digest
of its test's node id, to find that test. Any other test-runtime finding not seen counts as `inconclusive`; the report
lists it in `baseline.inconclusiveFindings` with the first reason that applies:

1. `recorded without its owner`: the entry was written before baselines recorded owners.
2. `the run's evidence is incomplete`: the run has an unknown reason or a failed session hook; or, for a max-queries,
   N+1 or unbounded-read entry, the `sqlite3` source lists evidence of untraced SQL in this run (`connections opened
   before capture started are not traced`, `connections opened before capture started could not be counted`, or
   `a connection factory or cursor class that does not subclass sqlite3.Connection / sqlite3.Cursor is not traced`);
   or, for an unbounded-read entry, the unbounded-read source lists a limitation.
3. `its test did not run`: no test of the run has the entry's owner (deleted, renamed or not collected).
4. `its test did not complete`: a call phase of its deciding attempt did not pass, or it never reached its call phase
   (skipped, a setup error).
5. `its test has a new finding of the same rule`: the finding's identity may have changed.
6. `its test still shows it outside the gate`: a marker, a fixture phase or a raised budget hides it from the gate. A
   `sharpit.max-queries` entry compares the queries of all phases of the attempt, summed, with its observed count here,
   although the gate counts only the call phase. A fixture that runs queries, such as one that seeds rows, therefore
   keeps a fixed max-queries entry inconclusive; clear it as described below. The other rules are checked phase by
   phase: N+1 is a pattern of repeated queries within one phase, so queries split across a fixture and the call phase
   are not summed.

Limits of this check: SQL a test sends through a driver beside SQLAlchemy (a raw `aiosqlite`, `psycopg`, `asyncpg` or
`pymysql` cursor; raw `sqlite3` is traced) is not traced, so an N+1 or query count moved onto such a cursor reads as
fixed. The `sqlalchemy` source note `<driver> calls outside SQLAlchemy are not traced` is listed whenever the driver
module is loaded, so it does not by itself make the evidence incomplete. Unbounded reads are recorded only in the call
phase, so an unbounded read moved into a fixture is not seen and its entry reads as fixed.

An advisor finding not seen counts as `fixed` when its advisor assessed the whole app, as before.
`--sharpit-write-baseline` combined with `--sharpit-baseline` keeps every inconclusive entry, so an entry is never
dropped on evidence the run did not have. The inconclusive entries are listed and kept also when an advisor entry is
carried and `fixed` is `null`; only a partial run reports `inconclusive` as `null`. An `inconclusive` count never changes the exit status. A baseline written
before owners were recorded makes every test-runtime entry inconclusive until it is rewritten once with both
`--sharpit-baseline` and `--sharpit-write-baseline` on a complete run, while those findings are still seen.

To clear an entry that stays inconclusive, for example one whose test was deleted, either rewrite the baseline without
`--sharpit-baseline` (with the `sharpit_baseline` ini option set, pass `--sharpit-baseline=`) on a complete run, which
also drops entries carried for an advisor that did not run in full, or delete its row from the baseline file, found by
the fingerprint the report lists.

## Accepted findings and required reasons

Individual tests can accept findings using `@pytest.mark.sharpit(...)`:

- Swallowed exceptions: `@pytest.mark.sharpit(allow_swallowed=True, reason="intentional fallback in mock")`
- N+1 queries: `@pytest.mark.sharpit(allow_n_plus_one=True, reason="batching covered by integration test")`
- Unbounded reads: `@pytest.mark.sharpit(allow_unbounded_read=True, reason="reference table with bounded size")`

The `reason=` keyword argument records the justification with the accepted finding across all outputs: the terminal summary, the JSON report (`sharpit-report/1`), and SARIF 2.1.0 output (under `suppressions` and `properties.reason`).

To enforce in CI that every accepted finding carries a non-empty explanation, use `--sharpit-require-reason` (or the ini option `sharpit_require_reason = true`). When enabled, any accept marker without a reason fails the session with a message naming the test and the marker. When disabled (the default), existing markers without reasons continue to behave as before.
