# Lane G6 — user-facing text (O3: for G4/integration to place; no README/SKILL edits here)

## pytest --sharpit: finding the application

You no longer need `--sharpit-app` for a typical suite. When no app was installed with `sharpit.install(...)` and no
`--sharpit-app` is given, sharpit looks at the modules your tests already imported and picks the FastAPI or
Starlette application defined there. It never imports a module and never runs module code to do this.

- It only considers your project's modules: modules installed under `site-packages`/`dist-packages`, the standard
  library, `conftest` and test modules (pytest's `python_files` patterns) are ignored.
- Apps mounted inside another app (directly, through middleware such as GZip, or under a host route) count as part of
  their parent.
- An app reachable from several modules is named after the shortest module name, so every xdist worker reports the
  same name.

The terminal summary says what happened:

```
sharpit: using app myproject.main:app (pass --sharpit-app to choose)
sharpit: several apps found (myproject.admin:app, myproject.main:app); pass --sharpit-app module:attr
sharpit: no application found; rest-api skipped (pass --sharpit-app module:attr)
sharpit: app myproject.main:app has no application routes; rest-api skipped (pass --sharpit-app module:attr)
```

`--sharpit-app module:attr` (or ini `sharpit_app`) always wins over the autodetected app. An app installed with
`sharpit.install` also wins: autodetect then does not run, including on other xdist workers.

## SKIPPED advisor status

When no single application is found, the REST API advisor is reported as `SKIPPED` (report `advisors[].status` and
`advisors[].apps[].status`) with the reason above. A skipped advisor does not make the session `unknown`, so a clean
suite with no web app finishes `pass` with exit code 0. SQL capture is judged on its own: a database driver sharpit
cannot trace still makes the session `unknown`.

Across xdist workers the advisor status is the worst of FAILED, UNKNOWN, SKIPPED, PASSED, in that order.

## --sharpit-require-app

```
pytest --sharpit --sharpit-require-app
```

or in `pytest.ini` / `pyproject.toml`:

```ini
[pytest]
sharpit_require_app = true
```

Restores the 0.3.0 behaviour: no application found (or several, or one without routes) makes the REST API advisor
`UNKNOWN` and the session `unknown`, which fails the run unless `--sharpit-allow-unknown`. Use it in CI when the
suite must assess an application.

## Quieter gate counts and --sharpit-verbose

By default `gate counts:` lists only findings that fail the gate: every test gate finding that failed its test
(N+1, query budget, exceptions), and advisor findings at or above `--sharpit-fail-on`. Advisor findings below the
gate are summarised in one line:

```
sharpit: 12 advisor notes in sharpit-report.json
```

`--sharpit-verbose`, ini `sharpit_verbose = true`, or pytest's `-vv` list every finding in `gate counts:` again. The
JSON report and the JUnit file always contain every finding, whatever the verbosity.

## Proposed spec §11 entry (deviation log)

> **0.4.0 G6 — app autodetect and `SKIPPED` (additive).** `sharpit-report/1` gains `"SKIPPED"` in the
> `advisors[].status` and `$defs.advisorApp.status` enums (additive; consumers that switch on status must accept it).
> With no `--sharpit-app` and no installed app, the pytest plugin autodetects one FastAPI/Starlette instance from
> loaded project modules; none, several, or one without routes now skips `rest-api` (`SKIPPED`, reason names
> `--sharpit-app module:attr`) instead of the 0.3.0 `UNKNOWN` "no application" reason. `--sharpit-require-app` /
> `sharpit_require_app` restores the 0.3.0 unknown. `_worst` ranks FAILED > UNKNOWN > SKIPPED > PASSED. Terminal
> `gate counts:` omits non-failing advisor findings unless `--sharpit-verbose`/`-vv`; JSON and JUnit content are
> unchanged by verbosity. One JUnit change: a test-runtime gate finding that failed its test is now a JUnit
> `<failure>` even when `--sharpit-fail-on` is above its severity (it was silently a pass under `CRITICAL`).
