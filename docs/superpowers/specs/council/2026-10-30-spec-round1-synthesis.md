# Council round 1 on the spec: synthesis

Reviewers: Codex gpt-6-luna (25 findings), Gemini 3.8 Flash via agy (25), Claude Opus subagent (24).

## Agreed by all three, fixed in spec rev 2
- Forwarded headers rewrite the ASGI peer, so a spoofed `X-Forwarded-For` could pass as loopback. Fix: forwarded headers + no trusted proxies → untrusted (§7.5).
- The host app's CORS middleware exposes sharpit GETs cross-origin. Fix: cross-site rejection on every method (§7.5, deviation).
- The dev-server signal had no algorithm. Fix: argv-based (§7.4).
- Instantiated pydantic-settings already merged its sources, so provenance was wrong. Fix: per-field env name + pydantic-settings order (§8).
- `defaultValue` leaked secrets from code defaults; `q` could probe raw values. Fix: mask defaults, mask before filter (§7.7).
- Bean naming and graph edges were ambiguous. Fix: `module:qualname`, dedupe by identity, every edge resolves (§8).
- Endpoints were missing (dismissed-rules, mcp-server toggle, auth/session). Fix: endpoint table (§8) + guard matrix (§7.6).
- Mount ordering and catch-alls, the scan outliving the MCP timeout, Overview fields, logger PlaceHolders and the KliperMedia factory command: all pinned.

## Rejected after checking
- Gemini #1: "spawned children see `--multiprocessing-fork`, not `--reload`". Checked with uvicorn on this machine: both reload and worker children see the full parent argv. The argv signal stands. Gemini's alternative (decide lazily at lifespan) is unnecessary.
- Codex #1 (FULL exposure contradicts the anti-goal): resolved by making FULL an explicit, logged opt-in exception rather than removing it.

## Coordinator's scope calls
- MCP is strictly read-only (no `vulnerabilities_scan` tool); the CLI client is deferred (endpoint kept).
- Runtime deps: starlette + packaging; own `.env` parser; CVSS ported from BootUI.
