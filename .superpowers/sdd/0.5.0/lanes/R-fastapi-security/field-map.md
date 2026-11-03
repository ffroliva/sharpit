# Field map: `spring-security` → `fastapi-security` (contract Wave B §3, Python mapping)

| BootUI key | sharpit source |
|---|---|
| `springSecurityPresent` | the host app is a `fastapi.FastAPI` (dependency trees exist) |
| `chains[]` | one per ASGI middleware stack: the app's own (`order` 0, `requestMatcher` `"any request"`, `requestMatcherType` `"ASGI middleware stack"`), then each `Mount` whose sub-app adds middleware (`"<prefix>/**"`, `"Mount"`) |
| `chains[].filters` | middleware simple class names, outermost first; sharpit's own hidden; options never read |
| `chains[].csrfEnabled` / `corsEnabled` / `sessionManagementPresent` | `starlette_csrf.*` or `asgi_csrf*` / `CORSMiddleware` / `SessionMiddleware` present |
| `auth.authenticationProviderTypes` | distinct `module.qualname` of `fastapi.security` schemes in any route's `Depends` tree, sorted |
| `auth.userDetailsServiceTypes` | `module.qualname` of each `AuthenticationMiddleware` backend (type only), sorted |
| `auth.configuredUsername` | always `null` (no analogue; `nullable.json`) |
| `handlerMappingAvailable` | same as `springSecurityPresent` |
| `endpoints[].method` / `pattern` / `handler` | route methods (HEAD folded into GET, `ANY` for a mount) / full mounted path / `module:qualname` |
| `endpoints[].rule` / `secured` / `roles` | classification: `unsecured`, `authenticated`, `hasAuthority` + sorted scopes, `permitAll`, `custom`, `unknown` (opaque mount) |
| `endpoints[].chainIndex` / `matcherDescription` | the stack serving the route (longest mount prefix) / its `requestMatcher` |
| `endpoints[].description` | `"Managed by <schemes>"`, the custom-guard or unreadable note, else `null` (`nullable.json`) |
| `endpoints[].bestEffort` | a route-level guard of unknown meaning, or the route could not be read |
| explain `matched` ... `filters` | first route (Starlette order) whose compiled pattern and methods accept the request |
| extra: explain `rule`, `roles`, `pattern`; report/endpoints `limitations` | sharpit additions (logged in handoff Decisions) |
