# Lane B-security: the `security` advisor

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes.

| | |
|---|---|
| **Lane id** | `B-security` (worktree `C:\development\github\sharpit-wt\0.5.0-B-security`, branch `lane/0.5.0-B-security`) |
| **Goal** | BootUI's security advisor for a FastAPI app: ~25 portable `SEC-*` rules over the `SecurityModel` and the app source, GET cached report, POST scan, paged violations. |
| **Spec** | §5, §5.4 |
| **Contract** | `BOOTUI-CONTRACT-0.4-WAVE-B.md` §1 (shared advisor contract), §2 (rules, DTOs, Python mapping, [JVM] drops); golden `security/captured.json` (pre-scan) + G0's `security/scanned.captured.json` if present |
| **Worker** | claude-flavio (Opus); reviewer codex |
| **Council** | **required** |
| **Depends on** | R-fastapi-security merged (consumes `SecurityModel`), F5 (`advisors/scan.py`, `appsource.py`) |
| **May touch** | `src/sharpit/engine/collectors/security/` (new package: `__init__.py`, `rules_auth.py`, `rules_transport.py`, `rules_config.py`, `rules_source.py`, `report.py`; each < 600 lines), `src/sharpit/engine/spi.py` (append-only, if a field is missing from `SecurityModel`), `src/sharpit/fastapi/introspector.py` (append-only: a read helper for middleware options, `vars()` only), `src/sharpit/fastapi/routes/security.py` (F stub), `src/sharpit/engine/panels04/security.py` + `ui/src/lib/panels04/security.ts` (flag only), `src/sharpit/engine/tools04/security.py`, `ui/src/views/Security.svelte` + test, `docs/security-advisor-checks.md` (new catalogue table), `tests/engine/collectors/security/`, `tests/fastapi/test_security_api.py`, `tests/safety/test_b_security_safety.py`, `tests/masking/test_b_security_masking.py`, `tests/test_security_docs_table.py`, `tests/fixtures/bootui/2.2.0/security/nullable.json`, the lane folder |
| **Must NOT touch** | `engine/appsource.py`, `engine/advisors/scan.py`, `settings.py` (F5's); guard, masking engine, activation |

**Architecture:** One `AdvisorScan` (F5) with this lane's rule list. Rules are pure functions
`(SecurityModel, SourceIndex | None, settings view) -> list[Violation]`. The adapter builds the `SecurityModel` and the
`SourceIndex` on POST only. Middleware options (CORS origins, TrustedHost hosts) are read as booleans/classes
("allows any origin", "credentials on"), never serialised as values (0.4.0 B decision).

## Review Focus

1. A violation message carries the rule, `file:line` or route, never a source literal or option value.
2. GET after scan opens no file and calls no introspection.
3. Every BootUI rule has a row in the catalogue: ported (P), new (N) or dropped ([JVM], with reason).

## Task 0: council and rule inventory

- [ ] **Step 1:** Rule inventory from WAVE-B §2 and BootUI `SecurityRules.java` into `docs/security-advisor-checks.md`:
  id, title (verbatim), P/N/[JVM], Python trigger. `/sharpit:llm-council --tier high` on the inventory and the
  architecture → `council.md`.

## Task 1: contract first

- [ ] **Step 1:** `test_report_golden_parity` (pre-scan against `captured.json`; post-scan against `scanned.captured.json`
  only if it exists, else `pytest.skip` with "post-scan golden absent (G0)" and the PARITY row says so).
  `nullable.json` for keys Python cannot fill, with reasons. `tests/test_security_docs_table.py::test_docs_table_matches_registry`.
- [ ] **Step 2:** Red commit `test: security advisor contract and catalogue`.

## Task 2: rules (one commit per category file)

For each category, a red commit with one test per rule (`# ported: SecurityRulesTests.<method>` where BootUI has one),
then the rules:
- auth: routes with no security dependency on a non-public path; docs routes exposed without one; mixed auth schemes.
- transport: CORS `*` with credentials; no TrustedHost; no HTTPS redirect when `--proxy-headers`-style deployment
  flags are absent (best effort, `bestEffort: true`).
- config: `debug=True`; `SECRET_KEY`-style settings with a literal default (`os.getenv("X", "dev-secret")`, the
  config collector's existing detection reused, not copied).
- source: hardcoded secrets in the app package via `appsource` (pattern list from the masking corpus).
- Each category's tests include `test_violation_never_contains_literal_secret` for its rules (the literal
  `sk-live-...` absent from message, preview and MCP output).

## Task 3: adapter, routes, MCP, safety

- [ ] **Step 1:** Tests: `test_get_after_scan_opens_no_source_file` (spy on `open`, `io.open`, `Path.read_text`,
  `Path.open` during the GET), `test_scan_reads_only_app_package`, `test_introspection_never_reads_or_calls_custom_route_attributes`
  (shared trap route), `test_read_only_blocks_scan`, `test_inactive_security_paths_404`,
  `test_security_get_no_side_effects`, `test_mcp_tools_list_has_only_get` (`get_security_report`,
  `get_security_rule_violations`; `security_scan` CLI-only).
- [ ] **Step 2:** Implement; flag on. Commit `feat: security advisor panel`.

## Task 4: view and live check

- [ ] Svelte view from BootUI `views/Security.vue` (behaviour reference), vitest; `/sharpit:live-verify` on
  `examples/fastapi_sqla`. Commit `feat: security advisor view`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/B-security/`: `council.md`, `handoff.md`, `findings.md`, `field-map.md`, `checklist.md`.
