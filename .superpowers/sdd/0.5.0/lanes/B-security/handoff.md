# Lane B-security handoff

Implementer: Claude Code (claude-opus-5-5, claude-flavio)

## Status

In progress. Done: Task 0 (catalogue, no council: the brief skips council tasks), Task 1 (contract), Task 2 (all four
rule categories), Task 3 service evaluation. Next: Task 3 wiring (routes, MCP/CLI tools, safety file, trap surfaces,
masking test, flag on), then Task 4 (Svelte view).

## Commits

| Task | Red | Fix |
|---|---|---|
| 0 catalogue | - | `0518ed5` docs |
| 1 contract | `298faee` | `b6c29d1` |
| 2 transport | `a5d6f3b` | `eb75c3f` |
| 2 auth | `c8e019a` | `e445775` |
| 2 config | `96ebb75` | `e537f77` |
| 2 source | `fc4a915` | `442a29b` |
| 3 scan | `e030f19` | `086a6e7` |

## Decisions

- 27 active rules (22 ported P, 5 new N), 27 dropped with reasons: `docs/security-advisor-checks.md`.
- Rule severities are fixed per rule (the core's `RuleDefinition`); SEC-AUTHZ-001 is INFO in Python (public routes are
  legitimate), as WAVE-B §2 proposes. SEC-CORS-006 stays LOW; the message says when credentials are on.
- Middleware options are read in the adapter (`FastApiIntrospector.security_facts`, appended) and leave only as fact
  names (`any_origin`, `credentials`, `short_secret`, ...): `SecurityFacts`/`MiddlewareFacts`/`SchemeUrl` appended to
  `engine/spi.py`. Only the root app's `user_middleware` options are read; a mounted sub-app's options are not.
- No `service.py`: the registry's `assess` points at `collectors/security/service.py`, and the pytest plugin would hand
  it an `ApiModel`; without the module the plugin skips the security assessment (`_assessor` returns None). The
  service lives in `report.py`.
- `build_inputs` uses `appsource.resolve_package_root` (asserted by `test_scan_uses_the_one_package_root_resolver`);
  a resolved `__init__.py` root is indexed as its package directory (the red's fake module had no `__path__`).
- Analyzer/disclaimer/messages: "Spring Security" -> "FastAPI security", "filter chain" -> "middleware stack"
  (WAVE-B [AMBIG]); keys `filterChains`/`filterChainsAnalyzed` kept, values are each stack's matcher.

## How to resume

`git log --oneline` on `lane/0.5.0-B-security`; tests under `tests/engine/collectors/security/`. Every uv command needs
`UV_LINK_MODE=copy`.
