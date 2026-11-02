# Lane B-fastapi-security handoff

Implementer: claude-subagent-opus (lane B-fastapi-security)
Lane plan: `docs/superpowers/plans/2026-11-01-sharpit-0.4.0/B-fastapi-security.md`
Branch / worktree: `lane/0.4.0-B-fastapi-security` in `C:\development\github\sharpit-wt\0.4.0-B-fastapi-security`, base `34f1689`.

## Status

- Task 0 predict: CAUTION 7/10 (`predict.md`, `be95ac5`); mitigations folded into the code.
- Task 1 model + classification: red `369dc4b`, fix `0d353cb`.
- Task 2 `security_model()`: red `6ca0044`, fix `3859499`, typing `2f8f203`.
- Task 3 routes, explain, MCP, safety, masking, `nullable.json`, engine flag: red `6060ab6`, fix `0460657`.
- Task 4 view + UI flag: red `eb03313`, fix `9eda51f`; evidence files (this folder).
- Red tables: `findings.md` (Python reds by SHA, UI reds under `Commit`).

## Gates (implementer, at `9eda51f` / suite at `0460657`, no Python change after)

- `uv run ruff check`, `uv run ruff format --check`: clean. `uv run pyright`: 0 errors.
- vitest: 35 files / 280 tests passed; `npm --prefix ui run check` (tsc) exit 0.
- Full pytest `-n 4` at `0460657` (log `0.4.0-integration/.superpowers/sdd/0.4.0/logs/B-fastapi-security-pytest.log`):
  4238 passed, 9 skipped, 1 failed, 2 errors. The 2 errors are `no_side_effects` teardowns that saw my own edits to
  `FastapiSecurity.svelte` / `handoff.md` during the run (not product behaviour; both green on rerun, 145 passed with
  `test_osv.py`, the safety matrix GET sweep and `test_surface_follows_flags.py`). The failure is
  `test_sql_trace_overhead.py::test_statement_overhead_budget` (50.4 µs vs 50 µs, noise 38.6 µs, loaded run; passes
  in isolation; this lane has no hot path). Budget untouched.

## Status: DONE_WITH_CONCERNS (llm-council not run; full-suite rerun on a quiet tree is the coordinator's gate)

## Live check

In-process (no server bound; COMMON forbids dev servers), `examples.fastapi_sqla.app.create_app(enabled="ON")`
through `TestClient`. The example has no OAuth2 routes (O3, example untouched), so every endpoint is `unsecured`:

- `GET /sharpit/api/fastapi-security` → 200, one chain `["GZipMiddleware"]`, `auth` lists empty, `limitations: []`.
- `GET /sharpit/api/fastapi-security/endpoints` → 200, `total: 10`, e.g. `GET /background` `unsecured`.
- `GET /sharpit/api/fastapi-security/explain?method=GET&path=/owners` → 200 `matched: true`, `rule: "unsecured"`.
- `GET /sharpit/api/fastapi-security/explain?path=nope` → 400 `{"error": "Invalid request"}`.

Request for the coordinator's `live-verify.md`: the same four requests against a running example, plus an app with an
`OAuth2PasswordBearer` route (the API tests cover that shape in-process).

## Needs from coordinator

1. `src/sharpit/ui/static/` not rebuilt (lanes never run `npm run build`).
2. The UI test lives at `ui/tests/component/fastapiSecurity.test.ts` (vitest include pattern), not beside the view.
3. No edit to `tests/conftest.py::_PATH_PARAMS` was needed (no path parameters).

## How to resume

`UV_LINK_MODE=copy` on every uv command; pytest logs under
`C:/development/github/sharpit-wt/0.4.0-integration/.superpowers/sdd/0.4.0/logs/`. `itsdangerous` is not installed:
tests use a local `SessionMiddleware` class, never Starlette's.

## Decisions (deviations from the lane plan)

1. `SecurityModel.middleware` → `chains: tuple[SecurityChain(prefix, middleware), ...]` (a chain per mounted sub-app
   with its own middleware, contract §3 Python mapping).
2. The plan's `matcher` callback is replaced by `SecuredRoute.path_regex` (Starlette `compile_path` source, built in
   the adapter); the engine runs `re.match` (engine rule 1: no Starlette import). Never `Route.matches()`.
3. One field `unknown_dependency` (the plan's `route_level_unknown` would always equal it): a route/router/app
   `dependencies=[...]` entry (`Dependant.name is None`) with no scheme in its tree.
4. Scopes read from `own_oauth_scopes` (FastAPI ≥ 0.120) or `security_scopes` (0.115), unioned along the path.
5. FastAPI's docs routes are not listed; a framework mount (StaticFiles) is `unsecured`, a user opaque mount `unknown`
   + `bestEffort` + a limitation.
6. Extra keys (pass parity): `limitations` on report and endpoints; explain adds `rule`, `roles`, `pattern`.
7. The high-tier llm-council was not run by the lane worker (brief asks for predict only); see `predict.md` §Council.

## Fix round 1 (Codex gpt-6-luna)

- Red commit: `95136a909eda60bc76c5ba01f280ca80c96f194c`.
- WIP reviewed: `0a4f22178bd9763df9b42b51ab9c8234511e84c1`.
- Current status: implementation in progress; targeted run `round1-targeted2.log` reported 16 failed / 32 passed. Failures include pre-existing assertions whose semantics conflict with the requested scheme-only `secured` rule, plus route traversal and modern FastAPI lazy-router behavior. Do not claim green until resolved.
- Fixes in progress: engine explain mount capture and best-effort propagation; custom route exact-type guard; scheme-less/optional dependency detection; cumulative middleware stacks; UI unique keys and empty-value defaults.
- Next: resolve remaining failures without changing any red test body; run UI checks, targeted tests, safety matrix, lint/format/type gates and full suite detached; commit final fix and update this handoff.

## Fix-round result (Codex gpt-6-luna)

Final status: DONE_WITH_CONCERNS; fix round is not merge-ready.
- Red: `95136a909eda60bc76c5ba01f280ca80c96f194c`.
- WIP reviewed: `0a4f22178bd9763df9b42b51ab9c8234511e84c1`.
- Fix commits: `3120361`, `4bf1302`.
- Changes made: no `effective_candidates` calls; exact-type custom-route handling; scheme-only secured classification; scheme-less/optional dependency best-effort; mount-aware explain; cumulative middleware stacks; lazy-router static expansion/limitation; UI duplicate keys and empty-input defaults.

Evidence:
- Targeted Python: 17 failed, 31 passed (`B-fastapi-security-round1-focused.log`). Several failures remain in security and shared route introspection.
- Safety matrix: `tests/safety/test_b_fastapi_security_safety.py` passed.
- Ruff check: fails only on the long line in the committed red test `tests/fastapi/test_fastapi_security_api.py:234`; red body was not changed. Format check reports this red file plus unformatted source before formatting.
- Pyright: 21 errors remain in `introspector.py`.
- UI type check passed; FastAPI Security vitest passed 7/7 after the duplicate-key change.
- Full suite at the round snapshot: 4,218 passed, 9 skipped, 37 failed (`B-fastapi-security-round1-full.log`); the remaining failures include this lane's security tests and shared introspector consumers.

Next: resolve the listed Python regressions and typing issues while keeping committed red bodies unchanged, then rerun all gates. No changes were made to review/gate files.
