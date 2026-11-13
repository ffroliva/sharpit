# The safety gate

`pytest --sharpit` runs sharpit's test-session gates and the REST API advisor. The run fails when a finding meets the
configured severity threshold (`--sharpit-fail-on`, default `HIGH`), or when sharpit cannot establish that the run was
fully observed. INFO findings and dismissed findings do not fail. With a baseline, existing findings do not fail; new
findings do.

Sharpit fails closed on unknown results. An incomplete capture, unreadable or malformed baseline, or other unknown
reason exits non-zero by default. `--sharpit-allow-unknown` permits unknown results, but does not permit findings that
meet the gate.

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
