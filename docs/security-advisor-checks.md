# Security advisor checks

The `security` panel (BootUI's Security advisor, `DOCS/SECURITY-CHECKS.md`) runs a fixed ruleset against the host
FastAPI application on an explicit scan (`POST /sharpit/api/security/scan`, CLI `sharpit security scan`). It reads:

- the security model the `fastapi-security` panel shows: middleware stacks, each route's `fastapi.security` schemes;
- the middleware options of the root application and of every mounted Starlette/FastAPI sub-app as facts ("allows
  any origin", "credentials on", "secret shorter than 32 characters"), never as values; a middleware instance wrapping a
  mount is reported as a limitation (its options are not read);
- the application's own package source through `engine/appsource.py` (never imported, bounded, read once per scan).

Nothing in the application is called: no dependency, endpoint, middleware or property runs. `GET /sharpit/api/security`
returns the last scan and opens no file. A violation names the rule and a route, a middleware or a `file:line`; it
never carries a source literal or an option value.

"Production-like" means an active profile (`SHARPIT_PROFILES`, `APP_ENV`, `ENVIRONMENT`) listed in
`disabled_profiles` (`prod`, `production` by default).

## Rules

`Port`: **P** ported from BootUI with a Python trigger, **N** new (no BootUI source), **D** dropped (reason given).
Titles of P rows are BootUI's, verbatim.

| id | title | category | severity | port | Python trigger |
|---|---|---|---|---|---|
| SEC-AUTH-001 | Password encoder must not store credentials in plain text | Authentication | CRITICAL | P | a passlib `CryptContext(schemes=[...])` in the app source lists `plaintext` or an `ldap_plaintext` scheme |
| SEC-AUTH-002 | Password encoder should not use a weak or legacy algorithm | Authentication | HIGH | P | a `CryptContext` whose default (first) scheme is a legacy one (`md5_crypt`, `des_crypt`, `hex_md5`, `hex_sha1`, ...) |
| SEC-AUTH-004 | Review the Boot property-backed default account | Authentication | MEDIUM | D | [JVM] `spring.security.user.*` has no FastAPI analogue |
| SEC-AUTH-006 | BCrypt password encoder should use an adequate work factor | Authentication | LOW | P | `CryptContext(bcrypt__rounds=N)` or `bcrypt.gensalt(rounds=N)` with a literal N below 10 |
| SEC-AUTH-007 | HTTP Basic authentication should run only over HTTPS | Authentication | HIGH | P | a route requires `HTTPBasic` and its middleware stack has no `HTTPSRedirectMiddleware` |
| SEC-AUTH-008 | hideUserNotFoundExceptions should stay enabled | Authentication | MEDIUM | D | [JVM] a `DaoAuthenticationProvider` flag |
| SEC-AUTH-009 | Do not run production on Spring Boot's auto-generated default user | Authentication | HIGH | D | [JVM] Spring Boot's generated user |
| SEC-AUTH-010 | Form login should run only over HTTPS | Authentication | HIGH | P | a route requires `OAuth2PasswordBearer` (password form login) and its stack has no `HTTPSRedirectMiddleware` |
| SEC-AUTHZ-001 | Every filter chain should enforce authorization | Authorization | INFO | P | an unsafe-method route (POST, PUT, PATCH, DELETE) with no security dependency in an app whose other routes are secured (an ordinary parameter dependency, such as a database session, does not count as one) |
| SEC-AUTHZ-002 | Avoid blanket permitAll authorization | Authorization | HIGH | P | the app has routes and none is secured: no required scheme, no custom dependency, no `AuthenticationMiddleware` |
| SEC-AUTHZ-003 | Application security should not be effectively disabled | Authorization | HIGH | D | merged into SEC-AUTHZ-002 (one Python signal) |
| SEC-AUTHZ-004 | Catch-all filter chains should be ordered last | Authorization | INFO | D | [JVM] filter-chain ordering |
| SEC-AUTHZ-005 | Broader authorizeHttpRequests matchers should not shadow narrower ones | Authorization | INFO | D | [JVM] `authorizeHttpRequests` matchers |
| SEC-CSRF-001 | CSRF protection should stay on for browser-automatic credentials | CSRF | HIGH | P | an unsafe-method route reads `APIKeyCookie` or runs under `SessionMiddleware`, and its stack has no CSRF middleware |
| SEC-CSRF-002 | CSRF protection should stay on for HTTP Basic authentication | CSRF | MEDIUM | P | an unsafe-method route requires `HTTPBasic` and its stack has no CSRF middleware |
| SEC-SESSION-001 | Session fixation protection should be enabled | Session management | HIGH | D | [JVM] Starlette's signed-cookie sessions have no server-side session id to fix |
| SEC-SESSION-002 | Session cookie should set the Secure flag | Session management | MEDIUM | P | `SessionMiddleware` without `https_only=True` |
| SEC-SESSION-003 | Session cookie should set the HttpOnly flag | Session management | MEDIUM | D | Starlette always sets `HttpOnly` on the session cookie |
| SEC-SESSION-004 | Review SameSite=None on the session cookie | Session management | LOW | P | `SessionMiddleware(same_site="none")` |
| SEC-SESSION-006 | Review bearer authentication saved in sessions | Session management | LOW | D | [JVM] `SecurityContextRepository` |
| SEC-SESSION-007 | Consider configuring concurrent session control | Session management | INFO | D | [JVM] `SessionRegistry` |
| SEC-SESSION-008 | Remember-me signing key should be sufficiently long | Session management | MEDIUM | P | `SessionMiddleware` `secret_key` shorter than 32 characters (the length is read, never the value) |
| SEC-HEAD-001 | HTTP Strict Transport Security should be emitted | Transport and headers | MEDIUM | D | response headers are set at runtime; the Pentesting panel checks them on live responses |
| SEC-HEAD-002 | X-Frame-Options (clickjacking protection) should stay enabled | Transport and headers | MEDIUM | D | as SEC-HEAD-001 |
| SEC-HEAD-003 | A Content-Security-Policy should be defined | Transport and headers | LOW | D | as SEC-HEAD-001 |
| SEC-HEAD-004 | X-Content-Type-Options should stay enabled | Transport and headers | LOW | D | as SEC-HEAD-001 |
| SEC-HEAD-007 | Security response headers should not be globally disabled | Transport and headers | MEDIUM | D | [JVM] `headers().disable()` |
| SEC-HEAD-008 | Review HSTS max-age below the framework default | Transport and headers | LOW | D | as SEC-HEAD-001 |
| SEC-HEAD-009 | Review permissive CSP script execution | Transport and headers | MEDIUM | D | as SEC-HEAD-001 |
| SEC-HEAD-010 | Cross-origin isolation headers should be considered | Transport and headers | INFO | D | as SEC-HEAD-001 |
| SEC-CORS-001 | CORS should not allow all origins | CORS | LOW | P | `CORSMiddleware(allow_origins=["*"])` without credentials |
| SEC-CORS-002 | CORS must not combine wildcard origins with credentials | CORS | HIGH | P | `allow_origins=["*"]` with `allow_credentials=True` (Starlette then reflects the request origin) |
| SEC-CORS-006 | CORS should not allow broad origin patterns | CORS | LOW | P | an `allow_origin_regex` that matches arbitrary hosts |
| SEC-METHOD-001 | Method security annotations require method security to be enabled | Method security | HIGH | D | [JVM] `@PreAuthorize` |
| SEC-METHOD-002 | Replace @EnableGlobalMethodSecurity with @EnableMethodSecurity | Method security | LOW | D | [JVM] annotation migration |
| SEC-ACT-001 | Actuator endpoints should not all be web-exposed | Actuator exposure | HIGH | D | [JVM] Actuator; the docs exposure is SEC-FAPI-002 |
| SEC-ACT-002 | Sensitive actuator endpoints should not be exposed | Actuator exposure | HIGH | D | [JVM] Actuator |
| SEC-ACT-003 | Exposed actuator endpoints should be protected by a security chain | Actuator exposure | MEDIUM | D | [JVM] Actuator |
| SEC-ACT-004 | Actuator health details/components should not be exposed unconditionally | Actuator exposure | LOW | D | [JVM] Actuator |
| SEC-ACT-005 | The actuator shutdown endpoint should not be enabled | Actuator exposure | HIGH | D | [JVM] Actuator |
| SEC-ACT-006 | Sensitive actuator endpoints should use an isolated management port | Actuator exposure | INFO | D | [JVM] Actuator |
| SEC-ACT-007 | Actuator env/configprops values must stay sanitized | Actuator exposure | HIGH | D | [JVM] Actuator; sharpit masks its own output |
| SEC-OAUTH-002 | Validate the JWT audience claim | OAuth2 / JWT | INFO | D | [JVM] `JwtDecoder` validators; FastAPI leaves token decoding to user code |
| SEC-OAUTH-003 | Review static verification-key rotation | OAuth2 / JWT | INFO | D | [JVM] `NimbusJwtDecoder` key source |
| SEC-OAUTH-004 | JWT issuer and JWK endpoints should use HTTPS | OAuth2 / JWT | HIGH | P | an `OpenIdConnect` scheme whose `openIdConnectUrl` is `http://` to a non-loopback host |
| SEC-OAUTH-005 | Opaque-token introspection must use HTTPS | OAuth2 / JWT | HIGH | D | [JVM] `OpaqueTokenIntrospector` |
| SEC-OAUTH-006 | OAuth2 client provider endpoints must use HTTPS | OAuth2 / JWT | HIGH | P | an OAuth2 scheme flow URL (`authorizationUrl`, `tokenUrl`, `refreshUrl`) is `http://` to a non-loopback host |
| SEC-CONFIG-001 | Spring Security debug mode should be off | Configuration | MEDIUM | P | `FastAPI(debug=True)`: Starlette returns tracebacks to the client |
| SEC-CONFIG-002 | H2 console should not be enabled in production | Configuration | HIGH | D | [JVM] H2 console |
| SEC-CONFIG-005 | Error responses should not leak stack traces or internal messages | Configuration | MEDIUM | D | merged into SEC-CONFIG-001 (`debug=True` is the Starlette traceback switch) |
| SEC-CONFIG-006 | Application should enforce HTTPS in production | Configuration | LOW | P | production-like profile and no `HTTPSRedirectMiddleware` on the app's own stack (best effort: TLS may end at a proxy; proxy headers do not count) |
| SEC-CONFIG-007 | Configuration should not hold literal secret values | Configuration | HIGH | P | `os.getenv("<secret-like key>", "<literal>")` or `os.environ.get(...)` with a literal default in the app source |
| SEC-CONFIG-008 | StrictHttpFirewall should not relax its default URL protections | Configuration | HIGH | D | [JVM] `StrictHttpFirewall`; the Host-header analogue is SEC-FAPI-001 |
| SEC-CONFIG-009 | Spring Security framework logging should not run at DEBUG/TRACE in production | Configuration | MEDIUM | P | production-like profile and the `fastapi`, `starlette`, `uvicorn` or `sqlalchemy.engine` logger at DEBUG (the level is read, never set) |
| SEC-FAPI-001 | Host header should be restricted to known hosts | Transport and headers | MEDIUM | N | no `TrustedHostMiddleware` on the app's stack, or one with `allowed_hosts=["*"]` |
| SEC-FAPI-002 | API documentation should not be public while the API is secured | Configuration | LOW | N | `openapi_url` is set and at least one route requires a security scheme |
| SEC-FAPI-003 | Proxy headers should be trusted only from known proxies | Transport and headers | MEDIUM | N | uvicorn's `ProxyHeadersMiddleware(trusted_hosts="*")` on the app's stack |
| SEC-FAPI-004 | Optional security schemes should not be a route's only check | Authorization | INFO | N | a route whose every scheme has `auto_error=False` and which has no other dependency |
| SEC-FAPI-005 | A route should not mix authentication schemes | Authentication | INFO | N | a route that requires schemes of more than one kind (e.g. `HTTPBasic` and `OAuth2PasswordBearer`) |
| SEC-SRC-001 | Source code should not hold literal secret values | Configuration | HIGH | N | a string literal in the app source that the masker's value detectors flag (JWT, PEM key, AWS key, vendor token, URL credentials), or a literal bound to a secret-like name (assignment, keyword argument, dict key, parameter default, `Field(default=...)`) |

BootUI's 26 reactive rules (`SEC-RXF-*`) and the Quarkus rules (`QS-*`) are [JVM] twins of the servlet rules above and
have no rows.
