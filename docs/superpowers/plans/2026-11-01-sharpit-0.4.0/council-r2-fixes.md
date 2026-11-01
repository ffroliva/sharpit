# Plan fixes after plan-council round 2 (coordinator's reconciliation, final)

Round 2 verdicts: claude approve with changes (M1–M6), agy approve with changes (3 majors), codex reject (3 majors).
Apply exactly these changes to the lane files you own; do not reopen decisions; verify every symbol against `src/` and
`tests/`. `council-r1-fixes.md` C1–C8 still apply except where amended here. PLAN.md and the spec are edited by the
coordinator.

## Ownership (no two lanes that can run at the same time edit the same file)

- **O1 `engine/sqla.py`:** owned by **A-postgresql** (the `run_db_read` keyword parameters, `bounded_read_only`). F
  creates the connection-event slot with an exact name and signature (F table row), e.g.
  `add_connection_listener(event: Literal["begin", "commit", "rollback", "savepoint", "rollback_savepoint",
  "release_savepoint"], fn: Callable[..., None]) -> Callable[[], None]` (returns a remover); **A-transactions never
  edits `sqla.py`**, it registers through the slot from its own collector module.
- **O2 Golden fixtures:** G0a writes only `tests/fixtures/bootui/2.2.0/<sharpit-id>/captured.json` (raw captures under
  `replica/evidence/2.2.0/<sharpit-id>/`, which is not mined). Panel lanes own `nullable.json`; a provisional fixture is
  `provisional.json`, written by a different worker than the lane. `tests/golden.py::assert_parity(sharpit_id, name,
  payload)` reads `captured.json` (or `<name>.captured.json` for a multi-endpoint panel) when present, else
  `provisional.json` and marks the result unverified. Amends C3.
- **O3 Shared docs and examples:** no panel or T-* lane edits `README.md`, `skills/sharpit/SKILL.md`,
  `examples/fastapi_sqla/` or `tests/test_example_app.py`. **F** wires `examples/fastapi_sqla` once for every committed
  and best-effort panel (`install(models=...)`, an optional OTel provider behind the test extra, any route a panel needs
  for its live check). A lane that needs user-facing text writes it to its lane folder `docs.md`; the final integration
  step (PLAN Step 5) merges those into README/SKILL in one commit. G4 keeps README/SECURITY/Dependabot.
- **O4 `implemented` flags without merge conflicts:** each 0.4 panel's flag lives in its own file:
  `src/sharpit/engine/panels04/<id_underscored>.py` exporting `IMPLEMENTED = False`, and
  `ui/src/lib/panels04/<id_underscored>.ts` exporting `implemented = false`; F creates all of them and the registries
  read them. A lane flips only its own two files. No lane edits `PANELS` or `nav.ts` lines.

## F (F-foundation.md)

- F table gains rows (name, file, signature): the O1 connection-event slot; **every pre-created settings field** with
  type, default and parser (incl. `security_logs_max_logs`, `postgresql_max_*`, `activity_unbounded_read_factor`);
  the post-split home of the `SqlTraceRecorder` construction; `CaptureState.security_logs: Any | None = None`; the
  401/403 hook `Callable[[Scope, int], None]` (consumers read `scope["method"]`/`scope["path"]`); `_load_app` and
  `_run_advisors` in `pytest_plugin/apps.py`; `autodetect_apps()` (one name everywhere).
- O3 example wiring and O4 flag files.
- **lane_gate red replay:** for every red-test name in `findings.md`: the test exists in the lane diff, passes at the
  lane head, and **fails** when run on the merge-base with only the lane's test files overlaid (a temporary worktree);
  else refused. Refusal tests: `test_lane_gate_refuses_fake_red`, `test_lane_gate_refuses_missing_red_test`.
- **Minimum cut at T0 + 2 h** (spec §10.6) is exactly: the three splits, O4 flags + the `implemented` surface test,
  `lane_gate.py` with its tests, the golden loader, the UI placeholders/wiring. Deferred to a follow-up lane `F-rest` (best
  effort, any worker): MCP stub modules, the `tests/safety/` and `tests/masking/` packages, test extras other than
  `psycopg[binary]`. Lanes that need a deferred piece create their own file for it (never a shared one).
- Checklist table: spec §6.1's ten items once each (remove the duplicate item 7).

## D1

- Per-finding dismissals: `DismissalStore.dismissed_pairs() -> set[tuple[str, str]]` of `(rule_id, identity)`;
  matching is `(f.rule_id, f.identity or f.target) in pairs` in `restapi/service.py::_run` (module-level function),
  `engine/advisors/report.py::apply_dismissals` and `testsession/gates.py::_finding`. Do not invent `dismissed_set()`.
- Correct names: `DismissalStore.list()` returns `list[str]`; the service holds `self.dismissals` (no `self._ctx`); the
  call sites are `service.py:132` (`report`) and `:137` (`scan`); D1 Task N produces `DismissalStorageError` (or drop it).
- D1 no longer gates G1G2: **whichever of D1 and G1G2 merges second** wires `dismissed_pairs()` into the plugin's
  dismissed set, with `test_per_finding_dismissal_reaches_gate`. Both lane files say so.

## G1G2

- Depends on **F and G6** only.
- May touch `engine/collectors/restapi/service.py`: an errored rule emits `RuleResult.skipped(rule)` + an unknown
  reason; `RestApiService.summary` counts `SKIPPED`.
- One predicate `testsession/gates.py::fails(dto: Mapping[str, Any]) -> bool` = not dismissed and `baselineState !=
  "existing"` and `severity != "INFO"`, used by `pytest_runtest_makereport` and `outcome._failing_tests`.
- `session_status` returns `SessionStatus(status, fail_reasons, unknown_reasons)` (a NamedTuple), and `exit_fails`
  reads `unknown_reasons`; say which call sites change.
- `test_schema_copies_identical` already exists: it is not a red; drop it from the reds. Replace the stale
  `pytest_plugin/__init__.py:241` reference with F's post-split module.

## G6

- xdist: each worker ships its autodetect candidates (`module:attr` names) in `workeroutput`; the controller decides
  uniqueness over the union across workers, and drops the `rest-api` runs when more than one distinct app appears. May
  touch `pytest_plugin/session.py` for the `workeroutput` key. `test_autodetect_ambiguous_across_workers_uses_none`
  (two workers, two apps).
- One function name: `autodetect_apps()`.

## A-postgresql

- Evidence: the **coordinator** runs the leased-database tests with its own `agentctl lease database` and writes
  `gate/leased-pg.log` (head SHA in the first line) in the integration worktree; a run where they skipped is
  **unverified** and does not meet the committed definition of done.
- `normalize_sql` (`capture/sqltrace.py:280`), not `normalize`; `engine_registry` is Optional; `engines()` yields
  `(name, engine)` tuples.

## A-transactions

- O1: no `sqla.py` edits; uses F's slot. Its own collector module only.

## A-data, A-sqlalchemy-statistics, B-security-logs

- O3: remove every edit to `examples/fastapi_sqla/`, `tests/test_example_app.py`, `README.md`, `skills/sharpit/SKILL.md`;
  write user-facing text to the lane's `docs.md`.
- B-security-logs: use `CaptureState.security_logs` and the hook `(scope, status)`.

## T-swallowed-exceptions

- Non-failing notes are findings with severity `INFO` (G1G2's `fails()` excludes them). Drop the claim that notes are
  counted in a notes line (that is G6's `terminal.py`, not this lane's).

## T-unbounded-read

- Compute `PagingContext` lazily from `scope` at the first counted load (the route match is not visible to the
  middleware up front); the factor travels in `Budget`; listen on `sqlalchemy.orm.Mapper` `load` and key counts by the
  `QueryContext` the event receives; note that objects already in the identity map do not fire `load` (an undercount,
  the safe direction).

## D2, G4, G3 (minors)

- D2 real symbols: `capture/exchanges.py::exchange_row`, `capture/sqltrace.py::entry_dto`, `SqlTraceRecorder.report`,
  `capture/logtail.py::SharpitLogHandler.line` (no `to_dto()` methods).
- G4: resolve the May-touch / Must-not-touch contradiction (`tests/docs/test_procurement_docs.py` is allowed).
- G3: `python -m sharpit.report summary` runs `src/sharpit/report/__main__.py`.
