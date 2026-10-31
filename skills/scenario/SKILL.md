---
name: scenario
version: "1.0"
description: >
  Use before implementing a sharpit feature or fix that touches activation, the guard chain, masking, a contract
  endpoint, MCP, introspection or the vulnerability scan. Walks ten sharpit-specific failure dimensions and produces a
  severity-ranked scenario table plus the tests that must exist before merge.
---

# `scenario`: edge cases on sharpit's failure surfaces

Happy paths are covered by the obvious test. This skill enumerates what breaks in a real developer's app but passes in
a unit test, and turns it into a must-cover test list for the plan.

## When to invoke

After `/sharpit:predict` returns GO or CAUTION, before `/sharpit:plan`. Also as lane step 2 of
`issue-resolve` (the reproduction, written at the root cause). Skip for docs, version bumps and scripts with no runtime
path.

## Invocation

```
/sharpit:scenario <feature or change>
```

## The ten dimensions

List only non-obvious scenarios. Skip a dimension only with a one-line reason.

**D1. Safe mode fails closed.** Invalid `SHARPIT_ENABLED` (`maybe`, `On `), profile spelling (`Production`, ` prod `,
`prod,dev`), a profile var set to an empty string, `SHARPIT_ENABLED=ON` together with a prod profile (enabled + warning),
`uvicorn --workers 2` without `--reload` (not a dev server), `fastapi run` vs `fastapi dev`, programmatic
`uvicorn.run(reload=True)` (not detected). When inactive, **every** method and path under the mount must 404 and
reveal nothing.

**D2. Activation and access guard.** Peer not loopback; `Host` malformed, absent, IPv6-bracketed, with a port, or
upper-case; `Forwarded`/`X-Forwarded-For`/`X-Real-IP` present with no trusted proxy (must be untrusted even from
127.0.0.1); `Sec-Fetch-Site: cross-site`; an `Origin` whose host differs; a missing, wrong or expired token; the session
cookie path under a `root_path`; per-panel and global read-only on write routes; guard order preserved.

**D3. Secret masking.** Sensitive names (`*_TOKEN`, `PASSWORD`, `api_key`), secret-looking values under innocent names
(JWT, PEM, AWS key id, URL userinfo), pydantic `SecretStr`/`SecretBytes`, `defaultValue` from
`os.getenv("X", "dev-secret")`, error messages and exception text, MCP `structuredContent`, the `q` filter used as a
probe (masking happens before filtering), `SHARPIT_EXPOSE_VALUES=FULL` (warning logged), the generated token (stderr
banner only, never `logging`).

**D4. BootUI contract parity.** Every key present including nulls, camelCase, epoch ms, no envelope; paging metadata
(`returned`, `matched`, `hasMore`) consistent; `limit` clamped to 1000, non-numeric → 400 `{"error": ...}`; reason and
error strings verbatim with the name substitution; a golden fixture asserts the shape; deviation logged in spec §14.

**D5. FastAPI/Starlette introspection drift.** Routers included with prefixes, `Mount`ed sub-apps, `APIRoute` vs
`Route`, websocket routes, dependency overrides, `Annotated` dependencies, lifespan vs on_event, a merged lifespan, the
floor versions (`fastapi 0.115`, `starlette 0.40`) and the newest; Python 3.12 to 3.14.

**D6. No side effects on GET or MCP.** No socket (`connect`, `create_connection`, `getaddrinfo`,
`gethostbyname`), no file created or modified under the cwd or `SHARPIT_STATE_DIR`, no logger level change, no
`os.environ` change. The `no_side_effects` fixture in `tests/conftest.py` is the test for this: every new GET route and
MCP tool gets one.

**D7. OSV/EPSS network failures.** OSV down, slow (timeout), 5xx, malformed JSON, partial batch, EPSS down while OSV is
fine; a second scan while one runs (409 `"sharpit action already in progress"`); the lock released after failure;
`scan.status` reports the failure with a message and the next scan works; `SHARPIT_VULNERABILITIES_OSV_ENABLED=false`.

**D8. Host-app integration.** Host `TrustedHostMiddleware`, `CORSMiddleware(allow_origins=["*"])`, auth middleware, an SPA
catch-all route (must not shadow the mount, which sits at `routes[0]`), a `root_path`, the host's own lifespan.

**D9. Scale and limits.** ~300 routes, ~80 getenv keys, ~200 distributions, very long values, deep logger trees, MCP
response-size caps (counted in UTF-8 bytes), MCP timeout releasing its semaphore.

**D10. MCP and CLI parity.** MCP and `{api}/cli` share `engine/tools.py`: same schema, same caps, same masking. MCP has
no action tool; `vulnerabilities_scan` exists only on `/cli`, gated by the panel and read-only. `SHARPIT_MCP_ENABLED`
off by default.

## Artifact

Write `docs/superpowers/plans/<YYYY-MM-DD>-<slug>-scenario.md` next to the plan `/sharpit:plan` will write, and commit
it with the plan. Do not leave the analysis only in the conversation.

```
# Scenario: <title>
## Coverage map (active dimensions, and why the others are skipped)
## Scenario table
| # | Dimension | Scenario | Severity | Expected behaviour | Test |
Severity: Critical (secret leak, active in prod, cross-site read, side effect on GET) · High (feature broken) ·
Medium (degraded, explicit error) · Low (cosmetic)
Test: Unit (engine, no I/O) · Integration (Starlette TestClient on a FastAPI app) · Golden (fixture shape) ·
Live (/sharpit:live-verify)
## Must-cover before merge (Critical + High): one pytest name per row, e.g. test_disabled_profile_case_and_whitespace
## Deferred (Medium + Low): file as issues
## Known-issues cross-reference
```

sharpit has no BDD layer: the "scenario" is a pytest function whose name states the behaviour. A ported BootUI case
keeps its `# ported:` citation.

## Next step

"Scenarios written. Next: `/sharpit:plan <feature>`, with the must-cover list as acceptance criteria."

Ported from gflow-cli's `scenario` skill; dimensions rewritten for sharpit.
