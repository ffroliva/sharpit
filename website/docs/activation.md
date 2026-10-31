# Activation

sharpit is a development tool, so it fails closed. With no reason to be on, every path under `/sharpit` answers a
plain 404 rendered by the host app's own 404 handler. The mount stays in place while inactive, as BootUI's does, so
sharpit still owns the paths under it: a host route such as `/{user}/...` cannot answer for `/sharpit/...`, and a host
with a catch-all or authenticate-first route answers `/sharpit/*` differently from its other paths (a 404 where it
would otherwise send 401), which shows that sharpit is installed. It switches on when the first of these applies:

1. `SHARPIT_ENABLED=ON` (always on; `OFF` always off).
2. An active profile is in `SHARPIT_ENABLED_PROFILES` (default `dev,local,development`). Profiles are read from the
   variables in `SHARPIT_PROFILE_VARS` (default `SHARPIT_PROFILES,APP_ENV,ENVIRONMENT`), so `APP_ENV=dev` works.
3. A reloading dev server is detected from the command line: `uvicorn ... --reload` or `fastapi dev`.

A profile in `SHARPIT_DISABLED_PROFILES` (default `prod,production`) wins over 2 and 3 and switches it off.
`uvicorn.run(..., reload=True)` from a script is not detected: set `APP_ENV=dev` or `SHARPIT_ENABLED=ON`.

When sharpit was asked for but ended up off, it logs the reason at WARNING; an explicit `OFF` or nothing asking for it
logs at INFO. When on, it prints a banner on stderr and `GET /sharpit/api/overview` reports the reason under
`activation`.
