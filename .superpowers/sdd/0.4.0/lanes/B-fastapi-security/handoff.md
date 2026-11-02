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
- Full pytest `-n 4`: see §Full suite below.

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
