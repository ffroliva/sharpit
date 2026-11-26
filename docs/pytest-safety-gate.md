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

A statement that the stdlib `sqlite3` driver refuses because it is not text did not run and is skipped. Through
SQLAlchemy, sharpit counts a refused `None`, `b""` or `0` statement as one statement with empty text, so it does not
make the run `unknown`. Any other statement that is not text (a query object passed to a cursor class or to
SQLAlchemy's `exec_driver_sql`) cannot be read, and the run is `unknown`: pass the statement as text, or use
`--sharpit-allow-unknown`.

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

## Accepted findings and required reasons

Individual tests can accept findings using `@pytest.mark.sharpit(...)`:

- Swallowed exceptions: `@pytest.mark.sharpit(allow_swallowed=True, reason="intentional fallback in mock")`
- N+1 queries: `@pytest.mark.sharpit(allow_n_plus_one=True, reason="batching covered by integration test")`
- Unbounded reads: `@pytest.mark.sharpit(allow_unbounded_read=True, reason="reference table with bounded size")`

The `reason=` keyword argument records the justification with the accepted finding across all outputs: the terminal summary, the JSON report (`sharpit-report/1`), and SARIF 2.1.0 output (under `suppressions` and `properties.reason`).

To enforce in CI that every accepted finding carries a non-empty explanation, use `--sharpit-require-reason` (or the ini option `sharpit_require_reason = true`). When enabled, any accept marker without a reason fails the session with a message naming the test and the marker. When disabled (the default), existing markers without reasons continue to behave as before.
