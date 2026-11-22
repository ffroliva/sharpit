# Safety model

- **Local only.** Requests must come from a loopback address with a loopback or allow-listed `Host`. A request
  carrying a forwarding or client-address header (for example `Forwarded`, `X-Forwarded-For`, `X-Real-IP` or
  `CF-Connecting-IP`) and no trusted proxy is configured counts as remote.
- **Cross-site requests are refused** on every method (`Sec-Fetch-Site: cross-site`, or, on API paths, an `Origin` that differs from
  the request's full origin: scheme, host and port; other paths compare the host), even when your app has `CORSMiddleware(allow_origins=["*"])`.
- **Remote access needs a token.** Only loopback, or the container gateway under
  `SHARPIT_TRUST_CONTAINER_GATEWAY=AUTO`, with no forwarded header skips the token. Callers admitted by
  `SHARPIT_ALLOW_NON_LOCALHOST=true` or by a `SHARPIT_TRUSTED_PROXIES` address (whose requests may carry a rewritten
  peer) must present the token as `Authorization: Bearer <token>`. Set `SHARPIT_AUTHENTICATION_TOKEN`; otherwise a
  token is generated per process and printed once to stderr. A browser trades it for an `HttpOnly; SameSite=Strict`
  cookie through `POST /sharpit/api/auth/session`.
- **Secrets are masked** (`******`) in values, defaults and suggestions, in API, MCP and CLI output, including pydantic `SecretStr`.
  sharpit masks any URL that carries userinfo, including a user name with no password
  (`https://<key>@o1.ingest.sentry.io/1`, `redis://admin@cache:6379`), because DSN-style keys sit in that slot. A
  harmless user name in a URL is shown as `******` too. That is intentional: sharpit errs towards hiding.
- **GET has no side effects.** No network call, no file write, no logger change. The vulnerability scan (OSV and EPSS)
  runs only on an explicit POST.
- **Fails closed.** When off, or in a `prod`/`production` profile (unless `SHARPIT_ENABLED=ON` forces it on, with a warning), the whole mount answers a plain 404 (see [Why does a plain `uvicorn app:app` give 404?](activation.md) for what that does and does not hide).

## If sharpit reaches production

sharpit is a development and test tool. It is not meant to run in production, but an app can ship with
`sharpit.install(app)` still in it. `tests/fastapi/test_production_use_case.py` pins what happens then:

- **No dev signal (a plain `uvicorn app:app`), or a `prod`/`production` profile:** sharpit is inert. Every path under
  `/sharpit`, reads and actions alike, answers 404. Your own routes are untouched, no SQL listener or log handler is
  attached, and nothing is written.
- **`enabled="ON"` hard-coded in `install()` (or `SHARPIT_ENABLED=ON`):** that is an explicit override, and it wins
  over a `prod` profile. sharpit logs *"Profile 'prod' is in SHARPIT_DISABLED_PROFILES but SHARPIT_ENABLED=ON forces it
  on."* at startup and then answers loopback callers only. Every remote request, reads and actions alike, gets 403.
  Do not ship `enabled="ON"`: use a dev profile or the dev-server signal so production never turns it on.

## Behind a TLS-terminating proxy

The Origin check compares scheme, host and port. If a proxy terminates TLS and forwards plain HTTP, uvicorn must see
the original scheme or browser POSTs from the UI are rejected. Start uvicorn with `--proxy-headers` and
`--forwarded-allow-ips` (or set `FORWARDED_ALLOW_IPS`) to the proxy's address, and add that address to
`SHARPIT_TRUSTED_PROXIES`. Requests through the proxy still need the token.

## Multiple workers and `--reload`

sharpit keeps its state in the process that serves the request. With `uvicorn --workers N`, gunicorn or `--reload`:

- **Token.** When `SHARPIT_ALLOW_NON_LOCALHOST=true` and no token is configured, each process generates its own token,
  so a token printed by one worker is rejected by the others and a reload invalidates the browser session. Set
  `SHARPIT_AUTHENTICATION_TOKEN` to a fixed value in these setups.
- **MCP switch, logger levels, scan cache.** The MCP on/off switch, the last scan result and logger levels changed in
  the panel live in memory per process, so each worker has its own. Dismissed vulnerability rules are shared because
  they live in `sharpit.yml`.

For a dev tool, the simplest setup is one worker.
