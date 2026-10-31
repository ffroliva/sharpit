# Dogfood: sharpit on KliperMedia (2026-10-31)

Plan Task 16, spec §11. sharpit `mvp` at `c9190fb`, installed editable into a local KliperMedia worktree.

## Verdict

All §11 done criteria pass on a real, large FastAPI application. No sharpit bug was found, so there are no `fix:`
commits. There are two observations below for the owner.

| §11 criterion | Result |
|---|---|
| `/sharpit/` loads | 200; `/sharpit` 307 to `/sharpit/`; the UI renders all 8 panels with no console errors |
| non-empty `properties` / `mappings` / `loggers` / `beans` / inventory | 92 / 358 / 158 / 52 / 143 packages |
| a secret-named variable is masked | every secret-named variable and the password-bearing `DATABASE_URL` show `******` (API, MCP, UI text) |
| a scan completes | OSV `SCANNED`: 143 packages, 0 skipped, 24 advisories, EPSS 16 of 21 CVEs scored, in 1.8 s |
| `KLIPER_ENV=production` → 404 | `/sharpit`, `/sharpit/`, `/sharpit/api/overview`, `/sharpit/api/config`, an asset and `POST /sharpit/api/mcp` all 404 (Host `localhost` and `127.0.0.1`) |

## Setup

- KliperMedia worktree `C:\development\github\klipermedia-sharpit-wt`, branch `local/sharpit-dogfood` from local
  `main` (`79e7e4837`). It is not committed or pushed. The uncommitted diff is `pyproject.toml` + `uv.lock`
  (`uv add --editable ../sharpit-mvp-wt`) and three lines appended to `src/kliper/adapters/web/fastapi_app.py`:
  `import sharpit` and `sharpit.install(app)` after the last router/policy install. KliperMedia has no
  `create_app` factory (coordinator ruling), so the command was `uv run uvicorn kliper.adapters.web.fastapi_app:app`.
- KliperMedia needed one setup step before it would import: `uv run python scripts/i18n.py compile` (the `.mo`
  catalogues are build output and are not in git).
- Database: a disposable `postgres:17-alpine` container `sharpit-dogfood-pg` on a leased port, DB `sharpit_dogfood`.
  KliperMedia's startup runs its own Alembic upgrade to head. From launch to "Application startup complete" took
  about 26 s in the dev run, against an empty DB. The container has been removed.
- Environment: everything was passed inline. The main checkout's `.env` was not copied, so no real KliperMedia secret
  was loaded. The settings were `KLIPER_ENV=development`, `SHARPIT_PROFILE_VARS=KLIPER_ENV,SHARPIT_PROFILES` and
  `KLIPER_ALLOWED_HOSTS=localhost,127.0.0.1`, with fake canary values in four secret-named variables and in the
  `DATABASE_URL` password. Every response body and the rendered UI text were checked for every canary value. None
  leaked.
- `--reload` was not used. On Windows a reload worker inherits the socket and outlives the killed parent. Activation
  came from the `development` profile ("Enabled by active profile 'development'"), not from the argv dev-server
  signal, so dropping `--reload` changed nothing.
- The run followed the multi-agent protocol: join, app-port/database/db-port leases, and a `docker-test --global`
  slot. That slot waited about 16 min behind a peer's full-suite lease. Everything was released at the end.

## Large-app behaviour

| Check | Result |
|---|---|
| App size | 113 top-level `app.routes` entries, mostly FastAPI 0.141 lazy `_IncludedRouter` objects. sharpit expanded all of them: 358 mapping rows, 0 without a method, 0 `<unexpanded include_router>` rows, sharpit's own rows excluded |
| Paging cap | `?limit=5000` returns the full set, all of which is under 1000 here. The cap (`MAX_LIMIT = 1000`) was not reached by any panel |
| API latency (warm) | panels 5 ms, overview 23 ms, mappings 30 ms, loggers 6 ms, beans 67 ms, inventory 2.4 s (first), scan 1.8 s |
| Config first call | **7.6 s** on the first request and 10 ms afterwards (see observation 1) |
| UI | first load 0.93 s; every panel about 0.8 s including an 800 ms settle wait; Config filter "SECRET" under 0.6 s; no console errors |
| Loggers | set `kliper` WARNING then reset: configured/effective WARNING/WARNING then null/INFO. A new name (`kliper.dogfood.probe`) set DEBUG then reset: DEBUG then null/INFO |
| MCP | toggle on → `initialize` 200 → `notifications/initialized` 202 → `tools/list` 200 (6 tools: `get_overview`, `get_config`, `get_mappings`, `get_loggers`, `get_beans`, `get_vulnerabilities_report`) → `get_overview`, `get_config` (query SECRET), `get_mappings` all `isError: false`, about 10 ms each → toggle off |
| Guards | a foreign `Host` gets 403 and a foreign `Origin` gets 403; the host app still serves `/` (200) |
| Production | sharpit printed no banner. Inside the whole `/sharpit` namespace, sharpit's inactive mount answers 404, which KliperMedia's own exception handler renders as `application/problem+json`. Outside it, `/other/x` gets the host's 401. So the 404 comes from sharpit and does not fall through to KliperMedia's `/{handle}/{monitoring}` catch-all |
| Overview | "Kliper API", FastAPI 0.141.1, Python 3.14.7, profile `development`, startup 14 111 ms, OpenAPI `/api/docs` |

## Observations (not bugs, for the owner)

1. **The Config panel's first load takes 7.6 s on KliperMedia.** The cost is the one-time `config_scan` walk of the
   `kliper` package for `os.getenv` keys. KliperMedia is large, and the walk reads files and parses them with `ast`.
   The result is cached (10 ms afterwards). It does not block anything else, but the first visit to Configuration
   feels slow. The scan is the likely cause, inferred from the cold/warm split; it was not profiled. The options are to warm it in the background after startup, or to document `SHARPIT_CONFIG_SCAN` for
   big apps. This was not changed: it is design behaviour, not a defect.
2. **The Config panel lists the whole process environment, not only the app's keys.** Unrelated secret-named
   variables from the developer's shell, such as other tools' tokens, appear by name. All of them were masked
   correctly. This is by design (spec §14: "environ"), but on a developer workstation the list is long and mostly
   noise.
3. Setting a level on a logger name that does not exist creates that logger, and it stays in the list (158 → 160
   after the probe). This matches Spring/Logback behaviour, so it was left as is.

## Screenshots

Playwright took screenshots of all 8 panels at 1440x900. None shows a secret value: masking held, and the page text
was checked against every canary. **They are not committed.** They show KliperMedia's internal variable names,
source paths and its dependency vulnerability list, which is the owner's private information and does not belong in
the sharpit repository. They stay in `%TEMP%\sharpit-dogfood-shots\` on the dogfood machine.

## Not checked

The authentication-token path (remote access) was out of scope for a localhost run. The Providers panel was checked
for counts only, not for the accuracy of each row. Light and dark themes were not compared.
