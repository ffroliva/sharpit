# Lane D4: `vulnerabilities`, `mcp-server`, `rest-api` drift to BootUI 2.2.0 (carried from 0.4.0)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes. Red rule: PLAN.md §Red rule.

| | |
|---|---|
| **Lane id** | `D4` (worktree `C:\development\github\sharpit-wt\0.5.0-D4`, branch `lane/0.5.0-D4`) |
| **Goal** | `vulnerabilities` (`runtimeReach`, `advisorySymbols`, `advisorySymbolSource`, CVSS v4.0 fallback, MCP compaction), `mcp-server` (`supportedProtocolVersions`, `cancellations`, `progressDropped`, `_meta.progressToken`), `rest-api` (`sampleLocations`, rules `RAPI-RESP-010`, `RAPI-RESP-011`, `RAPI-VALID-006`, `RAPI-VER-007`). |
| **Design** | `docs/superpowers/plans/2026-11-01-sharpit-0.4.0/D4-drift-vulns-mcp-restapi.md` governs; deltas below |
| **Worker** | codex gpt-6-luna; reviewer Opus |
| **Council** | not required |
| **Depends on** | F5a (rest-api now runs on the shared core; `advisors/` files), D2 (R0: `engine/tools.py`) |
| **May touch** | `src/sharpit/engine/collectors/vulns/{interpreter,cvss,service}.py`, `src/sharpit/engine/mcp.py`, `src/sharpit/engine/advisors/{rules,report}.py`, `src/sharpit/engine/collectors/restapi/{rules,service}.py`, `src/sharpit/engine/tools.py`, `tests/fixtures/restapi/rest_api_check_ids.txt`, the tests named in the 0.4.0 plan, `tests/fixtures/bootui/2.2.0/{vulnerabilities,mcp-server,rest-api}/nullable.json`, the lane folder `.superpowers/sdd/0.5.0/lanes/D4/` |
| **Must NOT touch** | `engine/advisors/scan.py`, `registry.py` (F5a's), OSV/EPSS network clients beyond the files above, guard |

## Deltas from the 0.4.0 plan

1. rest-api edits go through F5a's core hooks; `scan.py` is not edited (a needed change is a coordinator fix commit).
2. The `vulnerabilities` golden records a failed OSV scan (`scan.status: "ERROR"`, PKIX), so its items are unchecked:
   the PARITY row stays `unverified` until G0's recapture (O1).
3. OSV/EPSS network failure scenarios (skill D7) apply: the lane's tests cover OSV down, EPSS down, the lock released.

## Must-cover

`test_rest_api_new_rules_fire` (one per new id), `test_rest_api_golden_parity_after_drift`,
`test_mcp_server_golden_parity_after_drift`, `test_vulnerabilities_new_keys_present`, `test_osv_down_releases_lock`,
`test_mcp_compaction_masks`.

## Evidence

`.superpowers/sdd/0.5.0/lanes/D4/`: `handoff.md`, `findings.md`, `field-map.md`, `checklist.md`.
