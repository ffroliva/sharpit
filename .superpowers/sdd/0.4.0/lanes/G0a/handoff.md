# Lane G0a handoff

Implementer: claude-subagent sonnet

Status: DONE (fix round 1 applied; see findings.md) (live capture, not provisional). Branch `lane/0.4.0-G0a`, base `d37c6f2`.

## Commits

| step | SHA |
|---|---|
| red tests (4, see findings.md) | b6b1a4e |
| sanitiser + 40 fixtures + meta.json | 932df69 |
| evidence | next commit (`docs: G0a evidence`) |

## What exists

- `tests/fixtures/bootui/2.2.0/<sharpit-id>/captured.json` (+ `<name>.captured.json`) for 31 panels, from BootUI 2.2.0 live
  on tiny-ledger; `meta.json` (`bootuiVersion 2.2.0`, `uncaptured`, `provisional: []`). No `nullable.json`.
- Raw captures: `replica/evidence/2.2.0/` (gitignored, not committed: raw config holds machine env).
  Re-sanitise: `python scripts/sanitize_golden.py replica/evidence/2.2.0 tests/fixtures/bootui/2.2.0`.
- Capture script (not in repo): scratchpad `capture.py`; log `.superpowers/sdd/0.4.0/logs/G0a-capture.log` (integration).

## Decisions and caveats for the coordinator and panel lanes

- **No golden for `alembic` and `sqlalchemy-statistics`** (listed in `meta.json` `uncaptured`): tiny-ledger runs
  Liquibase and has no Hibernate statistics, BootUI answers 404. Request provisional goldens if those lanes need them.
- `http-probe` is POST-only: captured by probing `GET /bootui/api/panels`.
- 2.2.0 goldens are SHAPE goldens: each list of objects is reduced to one merged representative item (first non-null per
  key), scalar lists to 3, because F's loader compares every payload item against `expected[0]` only. Panel lanes add
  `nullable.json` where sharpit legitimately returns null.
- `dismissed-rules` / `dismissed-findings` captured empty (dismissing writes state into the reference app's project);
  `mysql` is `NOT_READ`, `exceptions/caught` has `available: false` (no agent). `postgresql` status `PARTIAL`.
- BootUI POSTs needed the Spring Security CSRF cookie+header; business calls went to `http://127.0.0.1:8080/api/v1`
  with the Keycloak token (`ledger-test`, fixture user `alice`, password from tiny-ledger docs, CA-verified TLS).
- Ran the app with `--management.endpoints.web.exposure.include=health,info,beans,conditions,configprops,env,loggers,mappings,metrics,startup,scheduledtasks`
  (run argument) so beans/loggers/mappings are non-empty. Generated `docker/tls/*` (gitignored) in the reference repo.

## Left running (do not stop; morning side-by-side check)

- Spring Boot app: Java PID **44112** (Maven parent 21540), port 8080, log `...\0.4.0-integration\.superpowers\sdd\0.4.0\logs\G0a-bootui-app.log`.
  Stop: `taskkill /PID 44112 /F` then `taskkill /PID 21540 /F`.
- Traefik container `tiny-ledger-traefik-1` (started by me): `docker stop tiny-ledger-traefik-1`.
- BootUI: `http://127.0.0.1:8080/bootui/api/*`.

## Gates (worktree)

ruff check, ruff format --check, pyright: clean. pytest: see below.

pytest -n 4 (full, detached, `...\logs\G0a-pytest.log`): 3571 passed, 5 skipped, 1 failed, 1 error. The two are
`tests/fastapi/test_capture_overhead.py::test_request_overhead_budget` (timing, run alongside the JVM app and 4 workers)
and `tests/fastapi/test_unimplemented_panel_surface.py::test_unimplemented_panel_gets_have_no_side_effects` (the
cwd-scan `.pyc` flake F recorded). Both pass when re-run alone (2 passed); neither touches G0a files.
