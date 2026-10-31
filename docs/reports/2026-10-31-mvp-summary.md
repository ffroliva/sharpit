# sharpit MVP: morning summary (2026-10-31)

Branch `mvp` in `ffroliva/sharpit`. Not merged and not published to PyPI.
The version stays `0.1.0.dev0` until you tag a release.

## What shipped

sharpit is a Python/FastAPI port of BootUI. It is a local-only developer console, mounted with one line:
`sharpit.install(app)`.

- **Engine and adapter.** The engine is framework-neutral (no Starlette or FastAPI imports). The FastAPI adapter serves
  BootUI's JSON contract at `/sharpit/api`.
- **Panels:**
  - Overview.
  - Configuration: env, `.env`, pydantic-settings and `os.getenv` keys, with provenance (file:line), masked.
  - Mappings.
  - Loggers: read, and set level.
  - Dependency graph ("providers").
  - Vulnerabilities: OSV, with EPSS scores and dismissals.
  - MCP server: off by default, read-only tools.
  - CLI endpoints.
- **New UI** at `/sharpit`, built with Svelte 5 under a strict CSP. It has a new look, a command palette, light and
  dark themes, and is keyboard- and axe-clean.
- **Fails closed.** sharpit stays off unless there is a dev signal, and a `prod`/`production` profile turns it off.
  When off, every path under the mount answers 404. It accepts loopback only by default. The Origin check compares
  scheme, host and port. Untrusted sources need a token, and that includes requests coming through a trusted proxy.
- **Packaging.** The wheel is 127 KB and the sdist 337 KB. The only runtime dependencies are `starlette` and
  `packaging`; FastAPI and pydantic-settings are extras. The project has a README, CHANGELOG, NOTICE (Apache, crediting
  BootUI and Julien Dubois) and CI: Python matrix, vitest, a UI build-freshness check and a wheel smoke test.

## Verification (HEAD of `mvp`)

| Check | Result |
|---|---|
| pytest | 1579 passed, 2 skipped |
| vitest | 90 passed |
| Playwright e2e | 16 passed, 0 axe violations |
| ruff, ruff format, pyright (strict) | clean |
| UI bundle rebuilt vs committed | identical |
| Parity (`replica/features.csv`) | 100/100, 30/30 must rows. The final review spot-checked 11 of 11. |

## How it was built

1. The spec and the plan were each reviewed by an LLM council: Codex, Gemini and Claude.
2. The plan was executed test-first in the worktree `C:\development\github\sharpit-mvp-wt`. Each of the 17 tasks went
   to a fresh subagent and then to a task review covering spec compliance and quality.
3. Your request for an overall assessment produced three assessors and three polish tasks:
   - backend safety and robustness;
   - UI;
   - developer experience (DX) and packaging.
4. The branch then went through the whole-branch review, `/code-review xhigh` and the ponytail review at xhigh.
   Every finding was fixed test-first and re-reviewed, or ruled as below.

## KliperMedia dogfood

Full report: [`docs/reports/2026-10-31-dogfood-klipermedia.md`](2026-10-31-dogfood-klipermedia.md).

- **It runs.** KliperMedia ran locally with sharpit enabled: 358 routes, 92 config properties, 158 loggers,
  52 providers and 143 packages.
  - The OSV scan took 1.8 s and found 24 advisories in KliperMedia's dependencies: 1 critical, 6 high.
  - MCP and logger set/reset worked, and all 8 panels rendered with no console errors.
  - None of the planted fake secrets leaked.
- **Production.** With `KLIPER_ENV=production`, every `/sharpit` path answers 404, including the MCP POST.
- **Nothing in KliperMedia is committed or pushed.** The local worktree is
  `C:\development\github\klipermedia-sharpit-wt` (branch `local/sharpit-dogfood`, uncommitted). It is kept for you to
  inspect.
- **Screenshots.** They are not committed, because they show KliperMedia's private variable names. They are in
  `%TEMP%\sharpit-dogfood-shots\`.
- **KliperMedia agent.** It was told through agentctl (`claude-speed-check`, the klipermedia-63 session) and gave us a
  Docker test window.

## Security fixes found late (all fixed, tested and re-reviewed)

- With `SHARPIT_MASK_SECRETS=false`, sharpit's own token showed in Config and MCP. It is now always masked, including
  with whitespace or embedded in a longer value.
- A spoofed `X-Forwarded-For` behind a trusted-proxy range could skip the token. Trusted-proxy traffic now needs the
  token. This is stricter than BootUI and recorded in spec §14.
- `SHARPIT_PATH=/` would have mounted sharpit over the whole host app. It is now rejected.
- Deeply nested JSON caused a 500. It now gets a parse error.
- A panel flag set to `None`, or misspelled (`readonly`), could leave a panel writable. Both now fail closed.
- The fix hint built a shell command from OSV data. It now only shows for safe characters.

## Calls for you

1. **The inactive mount stays.** While off, sharpit still owns the paths under `/sharpit` and answers a plain 404,
   which can differ from a host catch-all route. BootUI does the same. The alternative is to mount nothing when
   inactive, which removes the tell but diverges from BootUI.
2. **`--reload` anywhere in argv counts as a dev signal.** This keeps `gunicorn --reload` and `hypercorn --reload`
   dev setups working. The cost is that a non-dev `--reload` deployment activates sharpit. Loopback-only still
   applies, and a prod profile still wins.
3. **The KliperMedia security assessment you asked about is not started.** It is still waiting on your go-ahead.
4. **Merge and release.** README image links and the CHANGELOG compare link point at `master` and a `v0.1.0` tag, so
   they 404 until you merge and tag. CI runs on GitHub for `mvp`; its first runs caught a bad job condition, a
   locale-bound test and a too-low Starlette floor (now 0.44), all fixed.

All deviations from BootUI are in spec §14. The coordinator's rulings are below.

## Coordinator rulings

- **409 text.** It stays "sharpit action already in progress"; the UI matches it.
- **Cross-site navigation.** Opening `/sharpit/` from another site gets 403, because the cross-site check covers every
  method.
- **Forwarded headers.** Any forwarded header voids the loopback grant, and trusted-proxy traffic needs the token.
- **Masking:**
  - A URL with userinfo is masked even when the user name is empty.
  - The FULL exposure level keeps the `SecretStr` placeholder.
  - `masked` means the value was masked.
- **Config:**
  - Suggestions are filtered by `q`.
  - "Overridden by" is shown inside `resource`.
- **Vulnerabilities:**
  - `scannedAt` is null before the first scan.
  - EPSS keeps partial scores.
- **MCP.** BootUI's prompts are kept and rewritten for Python.
- **Panels.** Overview and CLI REST still answer when their panels are disabled, matching BootUI.
- **Loggers.** Setting a level on an unknown logger name creates it, matching Logback.
- **Dogfood.** It ran on `fastapi_app:app` (KliperMedia has no `create_app`), with its own Postgres container.

## Backlog (not done, by choice)

**Performance and concurrency:**
- Config first load took 7.6 s on KliperMedia (the AST scan). Warm it in a background thread; the README already
  shows how to narrow the scan.
- Saturated tool gates can exhaust anyio's 40-thread pool.

**Validation and masking:**
- Reject `nan`/`inf` duration kwargs.
- The settings-source fallback should compute `secret_typed` from the annotation.
- Vendor-prefixed tokens (`sk_live_`, `ghp_`) under harmless names are not masked.
- With masking off, a very short hand-set token over-masks substrings.

**UI:**
- Config table horizontal scroll below 420 px.
- Settings fields read from env are grouped with the OS variables; this needs an API flag.
- Grouped mappings, richer provider rows, palette actions, Overview health facts and a "configured only" logger
  filter.

**Docs and accuracy:**
- Overview says "FastAPI" on a plain Starlette host.
- Spec drift: `dev_signal()`, the §11 `create_app` wording and §15.2's `.env` parser.

**Tests:**
- The conftest side-effect guard should also compare `loggerDict` keys.
- Port `SecretMaskerTests`.
- Pin `/sharpitx`.
- Add a deadline to two test wait loops.

**Not built:**
- The `sharpit` CLI binary; only `/sharpit/api/cli` ships.
- Django and Flask adapters.

## Screenshots

`ui/tests/e2e/screenshots/`: every panel in light and dark, from the example app.
