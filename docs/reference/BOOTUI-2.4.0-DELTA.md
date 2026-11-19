# BootUI 2.3.0 to 2.4.0 fixture delta

The static fixtures under `tests/fixtures/bootui/2.4.0` come from `scripts/capture_bootui_24.py`, which is
`scripts/capture_bootui_23.py` with the pins changed (tag `v2.4.0`, commit
`0df7ed764688d04f83c246c9965e90158c1db488`, tag object `9374398c832d5c75b02329c96426a42652ad0a8d`). This document
compares them with `tests/fixtures/bootui/2.3.0`, file by file, and lists every difference with its BootUI source and
the lane that closes it.

The live per-panel goldens (every `<panel>/*.captured.json`, `ids.json`, the `enums.raw.json` files) are **not captured
yet** for 2.4.0. Tests that read live goldens stay on the 2.3.0 tree until that capture lands (decided by the presence
of per-panel folders).

## Static files

| File | Result | Detail |
|---|---|---|
| `meta.json` | as expected | New `bootuiVersion`, `commit`, `tag`, `tagObject`, `captured`, `command`; `app` and `profile` are `tiny-ledger` and `full` as before; `counts.starterMappings` 267 to 269 (see `routes.json`). |
| `panels.json` | identical | `BootUiPanels.java` is unchanged between the tags. |
| `properties.json` | identical | `BootUiProperties.java` is unchanged between the tags; the `defaultValueSource` line citations still hold. |
| `tools.json` | as expected | 116 tools in both; every `name`, `command`, `inputSchema`, `panel`, `action` and `stacks` is equal. Seven strings differ (below). |
| `routes.json` | **unexpected** | The `reads` and `actions` catalogs are identical (82 reads, 78 actions), so the set of BootUI actions is unchanged. The starter mapping cross-check differs (below). |
| `rule-ids.json` | as expected | 603 to 604 ids: `SEC-STATIC-001` is the single added rule; `DocsCommand` topic literals are excluded. |
| `rule-ids-diff.json` | follows `rule-ids.json` | `inJavaOnly` grows from 7 to 8 ids: `SEC-STATIC-001` added. |
| `bootui-tests.json` | as expected | Regenerated: 1128 test classes. |

### `tools.json`: the seven strings

Expected (`bootui-tools.json`, +7/-7). Lane A1 adopted the three descriptions for runtime insights and exceptions; the remaining three belong to lanes A2 and A3.

| Tool | Field | Change | Lane |
|---|---|---|---|
| `get_exceptions` | description | caught-exceptions wording | A1 |
| `get_runtime_insights` | description | wording | A1 |
| `get_runtime_insight` | description | explicit observation status | A1 |
| `get_transactions` | description | `propagation` values `NEW`, `REQUIRES_NEW`, `NESTED`, `UNKNOWN` | A2 |
| `get_security_report` | description | static-only report | A3 |
| `security_scan` | summary and description | static analyzer declarations (SpotBugs/FindSecBugs, Semgrep, a `sonar-project.properties` file, CodeQL) | A3 |

`tests/parity/test_tools_parity.py` records `get_exceptions`, `get_runtime_insights`, and `get_runtime_insight` in `DESCRIPTION_ADOPTED`, and pins the remaining three names as `DESCRIPTION_GAPS`, each with its lane.

### `routes.json`: unexpected, `StaticSecurityController`

The plan expected identical output. BootUI 2.4.0 adds
`bootui-spring-boot-starter/.../security/StaticSecurityController.java`, which maps `GET /security` and
`POST /security/scan` next to the existing `SecurityController` (its lines move from 46/51 to 52/57). The two new
starter mappings are the two paths of the static security tier. No route is added to or removed from the `reads` or
`actions` catalogs, and no panel prefix changes. Lane A3 decides whether sharpit mirrors the second tier.

### `rule-ids.json`: `SEC-STATIC-001` and excluded artefacts

- `SEC-STATIC-001` (expected): `bootui-engine/.../staticsecurity/StaticSecurityAnalysisDetector.java`. Lane A3. Not
  documented in `docs/*-CHECKS.md`.
- `CRAC-READINESS`, `GRAALVM-READINESS`, `JVM-TUNING`, `QUARKUS-ADVISOR`, `REST-API`: string literals in
  `bootui-cli/.../DocsCommand.java` (documentation topic names, lines 169-178). They match the script's rule-id
  pattern but are not rules. The capture script excludes `DocsCommand.java` literals by source and classifies only
  valid non-numeric `QS-*` identifiers.

## Change to the capture script beyond the pins

`SHA-512` appears for the first time in `src/main/java` (`bootui-cli/.../ReleaseRepository.java:90`, a digest algorithm
name). The 2.3.0 script classified only `SHA-256` as "an algorithm label in Java test inputs, not a rule identifier" and
aborted on `SHA-512` with `Unclassified independent rule id`. The unified capture script treats both as digest
algorithm labels (updating the reason text for SHA-256 as well). This is the only change beyond the pins.

## Metadata reproducibility

The capture script writes `app`, `profile` and the capture date directly, so `command` reproduces `meta.json`;
the hand-added `liveGoldens` key is dropped (existence of live goldens is decided by the presence of per-panel folders).

## Live files

Not captured yet for 2.4.0: `ids.json`, every panel folder (`activity` ... `vulnerabilities`), `emptyLists` and the
`uncaptured` map in `meta.json`. The expected live differences (`exceptions/caught`, `transactions`, `security`,
`database-advisor`, `cli`, `mcp-server`) stay unverified until then.

## Parity tests

| Test | Reads | Status |
|---|---|---|
| `test_tools_parity.py` | `2.4.0/tools.json` | moved; known description gaps recorded per lane |
| `test_properties_parity.py`, `properties_status.json` | `2.4.0/properties.json` | moved; identical file, no new difference |
| `test_routes_parity.py`, `routes_status.json` | `2.3.0` live goldens | stays on 2.3.0 |
| `test_rules_*_parity.py` | none (ported cases are inline) | no fixture to move; `SEC-STATIC-001` is a matrix row (A3) |
| `tests/docs/test_parity_matrix.py` | `2.3.0` tools, panels, routes status | stays; the routes column is computed from the 2.3.0 goldens |
