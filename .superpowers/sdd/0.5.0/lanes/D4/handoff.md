# D4 handoff: vulnerabilities, mcp-server, rest-api drift to BootUI 2.2.0

Implementer: Claude Code subagent (claude-opus-5-5)

- Base: c6e93d2 (release/0.5.0). Head: see `git log -1 lane/0.5.0-D4` (the evidence commit). Status: ready-for-review.

## Done

| Task | Red commit | Fix commit |
|---|---|---|
| 1 vulnerabilities keys, MCP compaction, get_threads default 25 | 130bda0a9e313d0c77af27728af93a36a9896048 | f3975137ca95859ce472f24a8df2fba47bae1191 |
| 2 mcp-server 2026-07-28, cancellations, progressDropped | 2068bf7d4f30c987d08b27300776958cee7cc53e | 9fe30d510d0d2b13651845003fbe54e02fa27879 |
| 3 rest-api 2.2.0 rules | 7fcebfe31cc76d912cd88ea1d866e4b103597bed | 2eb2b6ac81ccedf78d5204ba9d9710c9cbd8d40e |

Follow-up from the full suite: d236fd8ce700a9dd395bd5447bc3b1c6a559fac6 (frozen RESP-011 text and fingerprint rows,
2.2.0 vulnerabilities keys in `tests/test_conformance.py::NEWER_THAN_GOLDEN`, `mcp.py` prompts/get extracted to
`_get_prompt` so `_dispatch` stays under C901 10; the mcp.py baseline of 1 is unchanged).

Per-test reds and pins: `findings.md`.

## Must-cover

| Test | Exists | At head |
|---|---|---|
| tests/engine/restapi/test_restapi_rules.py::test_rest_api_new_rules_fire (4 params, one per id) | yes | pass |
| tests/engine/restapi/test_restapi_report.py::test_rest_api_golden_parity_after_drift | yes | pass |
| tests/fastapi/test_mcp_api.py::test_mcp_server_golden_parity_after_drift | yes | pass |
| tests/engine/vulns/test_service.py::test_vulnerabilities_new_keys_present | yes | pass |
| tests/engine/vulns/test_service.py::test_osv_down_releases_lock | yes (pin) | pass |
| tests/masking/test_d4_masking.py::test_mcp_compaction_masks | yes | pass |
| tests/engine/test_tools.py::test_get_threads_default_limit_is_25 | yes | pass |

## Gates (lane worktree, head before the evidence commit)

At d236fd8ce700a9dd395bd5447bc3b1c6a559fac6: `ruff check` clean, `ruff format --check` 688 files formatted, `pyright` 0
errors, full `pytest -n 4`: 5463 passed, 28 skipped (log outside the worktree:
`0.5.0-integration/.superpowers/sdd/0.5.0/logs/D4-pytest.log`). The first full run (at 2eb2b6a) also failed
`tests/engine/test_n_plus_one_overhead.py::test_sqlalchemy_lazy_relationship_hook_overhead_budget` under machine
load (45 us vs 35 us budget, noise 35 us); it passed twice alone and in the rerun; D4 touches no SQLAlchemy code.

## Decisions and questions for the coordinator

1. **Outside May-touch: `src/sharpit/engine/tool_dispatch.py`** (one line in `_normalized_arguments`). The dispatcher
   was split out of `engine/tools.py` after the 0.4.0 plan (8c95dd8, 526e53f); an absent `limit` always became the
   via's max results there, so neither `get_threads`' 25 nor `get_vulnerabilities_report`'s 10 was reachable from
   `tools.py`. Fix: `Tool.default_limit` (tools.py) read by the dispatcher, capped by max results as before; the
   BootUI schemas are unchanged. Please accept or rule (`--allow-path` if the gate flags it). The default applies
   to MCP and CLI alike (the dispatcher is shared).
2. **Outside the plan's test list:** `tests/engine/restapi/test_restapi_findings.py` gained RAPI-RESP-011 rows
   (`test_cases_cover_every_rule` requires one per rule) and `tests/test_conformance.py::NEWER_THAN_GOLDEN` the
   vulnerabilities 2.2.0 keys (the 1.17.0 golden predates them), both extensions of existing pins.
3. **`sampleLocations` stays `[]`** (F5a-core's default). The golden's location shape is
   `{className, memberName, kind, sourceFile, line, sourcePath, precision}`, not the drift doc's `{file, line, uri}`.
   Filling it needs a location on `advisors/findings.Finding` and in `advisors/scan.py::_scan_once` (both outside
   D4: scan.py is F5a's), and a line number would mean resolving the endpoint object or reading source on a read
   path. An empty list is the honest "no violation has a location". Parked for a follow-up owning scan.py.
4. **CVSS v4.0 score selection parked.** CVSS v4.0 has no closed-form equation (macro-vector lookup table, ~270
   entries); BootUI's calculator is not available locally, and the existing pin
   `tests/engine/vulns/test_interpreter.py::test_cvss_v4_only_falls_back_to_database_label` asserts today's
   fallback. Changing it is a design call for the owner.
5. **RAPI-RESP-010, RAPI-VALID-006, RAPI-VER-007 are SKIPPED** (reasons in `SKIPPED_RULES`). The 0.4.0 plan put
   VER-007 in RULES, but FastAPI has no `consumes` condition, and the drift doc's analog (body on GET/HEAD/DELETE)
   is already RAPI-MAP-007. Two rules for one finding would double-count. RESP-011 is ported: a GET whose declared
   response is `X | None` with the default status.
6. **`cancellations`** counts `notifications/cancelled` (plan review focus 2). Calls are synchronous, so a cancel
   cannot stop one; the comment in `mcp.py` says so. **`progressDropped`** is always 0 (no progress notifications are
   sent). `_meta.progressToken` is accepted and ignored (`test_mcp_progress_token_in_meta_is_accepted`).
7. **Masking in the compacted MCP view**: `scan.message`, advisory `summary` and `details` go through
   `masker.mask_text` (an OSV failure message can carry proxy credentials). The REST GET report is unchanged.
8. The `vulnerabilities` golden is a failed-scan capture (items unchecked): its PARITY row stays `unverified`
   until G0's recapture (plan delta 2). `nullable.json` lists `scan.scannedAt` (null before a scan, contract §8).
9. No new route, so no safety-matrix ROWS change. `get_vulnerabilities_report` takes optional arguments only: no
   TOOL_ARGS/TOOL_SEEDS.

## Resume

Nothing open. Next: coordinator review + gate.
