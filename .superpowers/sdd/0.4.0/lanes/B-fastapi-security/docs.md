# User-facing text for the owner (O3)

- Panel `fastapi-security` (BootUI `spring-security`): the app's ASGI middleware stacks (CORS/CSRF/session flags),
  the `fastapi.security` schemes and `AuthenticationMiddleware` backends in use, every endpoint's rule
  (`unsecured`, `authenticated`, `hasAuthority` + scopes, `permitAll` for `auto_error=False`, `custom` for a
  route-level guard, `unknown` for an opaque mount), and `explain?method=&path=` (which route and rule a request hits).
  Static: no dependency, scheme, middleware or route matcher is called; middleware options (CORS origins, hosts,
  secret keys) are never read or shown.
- SKILL row: `fastapi-security` — "who can call each endpoint, read from the Depends tree without calling it".
- Rename: BootUI `spring-security` is `fastapi-security` (API path, MCP `get_fastapi_security`, CLI
  `fastapi-security`); the Spring DTO key names (`springSecurityPresent`, ...) are kept for parity.
