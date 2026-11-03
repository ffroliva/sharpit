# Predict: Lane B-fastapi-security (BootUI `spring-security` → `fastapi-security`, static)

Run of `skills/predict/SKILL.md` on the lane plan (`docs/superpowers/plans/2026-11-01-sharpit-0.4.0/B-fastapi-security.md`),
contract `docs/reference/BOOTUI-CONTRACT-0.4-WAVE-B.md` §3, the goldens under
`tests/fixtures/bootui/2.2.0/fastapi-security/`, and the code it touches (`fastapi/introspector.py`, `engine/spi.py`,
the F stubs). Personas written in turn, each before reading the next. Installed: fastapi 0.162.0, starlette 1.10.0;
floor `fastapi>=0.115`, `starlette>=0.44`.

## Verdict: CAUTION   Confidence: 7/10

## Summary

The panel is a read of objects FastAPI already built at import time (`app.user_middleware`, `APIRoute.dependant`);
nothing is called. The risk is all at the edges: a user object whose attribute read runs code, middleware kwargs that
hold secrets, and FastAPI internals that changed between 0.115 and 0.162 (`security_requirements`/`security_scopes` →
`own_oauth_scopes`). With the mitigations below it is safe to build.

## Persona findings

### Architect: GO (8/10)
- Reading lives in `FastApiIntrospector.security_model()` (adapter); DTO assembly in `engine/collectors/appsecurity.py`.
  The `AppIntrospector` Protocol stays unchanged: the engine reaches the method with `getattr(ctx.introspector,
  "security_model", None)` and treats a missing method or an exception as "absent".
- The engine cannot import Starlette (rule 1), so the explain matcher cannot use `compile_path` there. Smallest seam:
  the adapter stores each route's compiled regex **source string** on `SecuredRoute.path_regex` (built with
  Starlette's `compile_path` on the full mounted path, framework code); the engine runs `re.match`. This replaces the
  plan's `matcher` callback (one fewer moving part; same "never `Route.matches()`" guarantee).
- Two mounted sub-apps with their own middleware need a chain per mount, so `SecurityModel.middleware` becomes
  `chains: tuple[SecurityChain, ...]` (`prefix`, `middleware`). `route_level_unknown` and `unknown_dependency` would
  always be equal under the definition below: one field, `unknown_dependency`.

### Security: CAUTION (7/10)
- Side effects: no dependency, scheme, middleware, convertor or `matches()` is called. Scheme detection uses
  `issubclass(type(call), SecurityBase)` (never `isinstance`, which reads a user `__class__`); `auto_error` via
  `inspect.getattr_static` (a property on a user subclass is not run; non-bool → treated as `True`).
- Secrets: `Middleware.kwargs`/`args` are read only to find the `AuthenticationMiddleware` backend, and only its
  **type** leaves (`module.qualname`). CORS origins, TrustedHost hosts and `SessionMiddleware.secret_key` never reach
  any output. Pinned by `test_middleware_values_never_exposed` and the masking row.
- Explain input is attacker-shaped only through the guarded API: `path` must start with `/` and be ≤ 2048 chars, else
  400 `{"error": "Invalid request"}`; matching is a precompiled regex (Starlette convertor regexes, no backtracking
  blow-up beyond Starlette's own routing).
- sharpit's own mount and middleware (module `sharpit.*`) are hidden; explain on a sharpit path returns
  `"sharpit endpoints are hidden from this report"`.

### Contract parity: CAUTION (7/10)
- Keys verbatim from the Spring DTOs (`springSecurityPresent`, `chains`, `auth`, `handlerMappingAvailable`, ...);
  golden `captured.json` (report) and `endpoints.captured.json` cover the shapes. `configuredUsername` is always null
  (no analogue) → `nullable.json` entry with the reason.
- Extra keys, logged: explain adds `rule`, `roles`, `pattern` (what a FastAPI user needs); report and endpoints add
  `limitations` (why the read is partial). Extra payload keys pass `assert_parity`.
- Deviation already logged in spec §8.1/§11: static on GET (BootUI calls matchers and authorization managers).

### Host-app compatibility: CAUTION (6/10)
- Scopes: FastAPI 0.162 stores them on `Dependant.own_oauth_scopes`; 0.115 on `Dependant.security_scopes` (accumulated).
  Read both with `getattr` defaults and union along the path from route to scheme. Scheme sub-dependants exist in
  both versions (`call` is the scheme instance).
- Route-level `dependencies=[...]` (route, router, app) appear in `dependant.dependencies` with `name is None`; that is
  how "route-level unknown" is detected, read with `getattr`.
- A route whose dependant read raises → one limitation line, the route listed as `unknown`/`bestEffort`; the panel
  never 500s. Plain Starlette app → `springSecurityPresent: false` + reason
  `"FastAPI security dependencies are not available: the app is not a FastAPI app"`.
- 300 routes: one walk per GET, no network; endpoints is not paged in BootUI either.

### Devil's Advocate: GO (7/10)
- Smaller path considered: drop explain. Rejected: it is one of three BootUI endpoints and the matcher is ~10 lines on
  the precompiled regex.
- The `custom`/`bestEffort` rule could mark every `Depends(get_db)` route as best effort; restrict "unknown" to
  route-level dependencies (`name is None`) with no scheme in their subtree, which are the ones that are guards.

## High-confidence risks (2+ personas)
1. FastAPI internals drift (Architect, Host-app): every read via `getattr` defaults, per-route `try`.
2. Secrets in middleware kwargs (Security, Contract): only class names and the backend type leave.

## Conflicts resolved
- Plan's `matcher` callback vs engine rule 1: regex source on the model (Architect); no Starlette import in the engine.

## Required mitigations (CAUTION)
1. `issubclass(type(call), SecurityBase)` and `getattr_static` for user objects; nothing called (Task 2 sentinel test,
   nested two levels).
2. Middleware values never read except the auth backend's type (Task 3 test + masking row).
3. Scopes read from both `own_oauth_scopes` and `security_scopes`; drift test monkeypatches the tree to raise.
4. Explain input validation (400) and hidden sharpit paths (Task 3 `test_explain_input_edges`).

## Council

The lane brief for this continuation (`briefs/B-fastapi-security.md`) asks for the predict workflow only; the
high-tier `llm-council` (Codex + Antigravity) was not run by the lane worker (no external harness in this subagent's
remit). The coordinator's review of the lane (another family + `ponytail-review`) is the cross-family check.

## Recommended next step
Build Task 1 with the model changes above, then Task 2's sentinel tests before any route exists.
