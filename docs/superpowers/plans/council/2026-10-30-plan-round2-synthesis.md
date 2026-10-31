# Plan council round 2: synthesis

Reviewers: Codex (gpt-6-luna, 17 findings), Gemini (gemini-3.8-flash-high, 20), Claude (20). All three said "not executable as written"; all findings below were applied to the plan in the same commit.

## Agreed by two or three reviewers (all applied)
- Bare `/sharpit` never reaches a Starlette `Mount` (Gemini, Claude; Claude verified on Starlette 1.0.0): host 307/200, guard bypassed, inactive 404 broken. Fix: `SharpitMount` with regex `^{path}(?:/(?P<path>.*))?$`; tests for bare path inactive and guarded.
- `OsvAdvisoryInterpreter` had no owner (Gemini, Claude). Fix: `vulns/interpreter.py`, port `OsvAdvisoryInterpreterTests`; `querybatch` returns `QueryResult` (failed, truncated) for PARTIAL.
- Config panel wrongly action-capable (all three). Fixed.
- Session cookie named two ways (Codex, Claude). Single constant `SESSION_COOKIE = "SHARPIT_SESSION"`.
- CI `ui` job red before Task 15 (Gemini, Claude). Guarded by `hashFiles`.
- Task 15 too big (Gemini, Claude). Split 15a/15b/15c; e2e after Task 14 with lease and background lifecycle.
- Golden truncation breaks `page` and `severityCounts` (Codex, Gemini). No truncation; recursive secret check.
- `LocalhostGuardTests` not portable one for one (Codex, Claude). Case list labelled same / inverted / dropped.
- Masking corpus and no-side-effects spy too weak (Codex, Claude). Named plants under sensitive and harmless names, every route incl. errors, token-to-stderr tests; spy snapshots files, blocks DNS, compares logger levels; every GET from the route table.
- CLI outcomes and `prompts/get` untested (Codex, Claude). Table-driven CLI test; `prompts/get`; action tool over MCP → `-32602 Unknown tool`.
- Dismissal YAML injection (Codex, Claude). Rule-id regex, BootUI file format, atomic write.
- Host `TrustedHostMiddleware` cannot be bypassed (Codex). Documented as authoritative; test with `localhost` allowed.

## Single-reviewer findings applied
- Claude: `trust_container_gateway` default must be OFF (BootUI default; AUTO exposes Docker LAN clients). Env names follow `SHARPIT_<BOOTUI PROPERTY>` (`SHARPIT_VULNERABILITIES_*`); CLI caps added; durations; EPSS base. Fail-safe table for invalid values; settings warnings reach activation. `ConfigServiceTests` ported; KeywordPatternMasker has no upstream test (derived). Task 7 split 7a/7b/7c with per-source provenance algorithm. `SingleFlight` worker-thread contract with `WaitTimeout`. `CallContext` with request scope for tools. Bean classification enum incl. BOOTUI; lifespan bean is the host's. Install budget test moved to Task 14. Inactive 404 matches host body. uvicorn `ProxyHeadersMiddleware` spoof test. `lowest-direct` resolution job. KliperMedia stop condition and `KLIPER_ALLOWED_HOSTS`.
- Codex: custom `path`/`api_path` with segment-boundary validation; argv cases listed exactly; dogfood server stop/start order.
- Gemini: `PanelSettings` defined; `ctx.app_settings`; `aliases` always present; dismissal recompute test; `toolCount == 6`; `health.json` excluded from conformance; `serverPort` None-safe; suggestions filtered by `q`.

## Rejected
- Codex #1 "pushing `mvp` contradicts never push": the owner's goal requires the branch on ffroliva/sharpit. Constraint reworded: only the coordinator pushes, only `mvp`.
- Codex #10 "impeccable / frontend-design skills unavailable": both are installed in Claude Code; kept with a fallback for harnesses without them.
- Gemini #16 remove the KliperMedia worktree: kept for the owner to inspect (local, unpushed).
