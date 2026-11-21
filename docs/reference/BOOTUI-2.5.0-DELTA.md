# BootUI 2.4.0 to 2.5.0 static fixture delta

The static capture uses BootUI tag `v2.5.0` at commit `c4458db8dd18c08074119f22a79dda3e714abbda`. The fixtures are generated with `scripts/capture_bootui.py --version 2.5.0` from the BootUI source tree.

## Captured fixture changes

| Fixture | BootUI 2.4.0 | BootUI 2.5.0 | Source or reason |
|---|---:|---:|---|
| Panels | 65 | 65 | `BootUiPanels.java`; the panel catalogue is unchanged. |
| Tools | 116 | 116 | `bootui-cli/src/main/resources/bootui-tools.json`; `get_mappings` adds `basePath` wording and `get_request_profile` adds authorization wording. Their sharpit descriptions remain documented gaps for A2 and B4. |
| Route contracts | 82 reads, 78 actions, 269 starter mappings | 85 reads, 78 actions, 269 starter mappings | `BootUiApiContractCatalog.java`; the three added reads describe exception occurrences and their binding diagnostics. |
| Properties | 209 | 212 | `BootUiProperties.java`; adds `bootui.vulnerabilities.scan-timeout=60s`, `bootui.http-exchanges.expose-request-id-header=true`, and `bootui.cli.instances-dir` with no default. |
| Rule identifiers | 604 | 688 | Rule registries and `RestApiRules.java`; the captured union increases by 84. `rule-ids-diff.json` records 0 documentation-only and 32 Java-only identifiers. |
| Test inventory | 1,128 classes, 10,927 methods | 1,144 classes, 11,204 methods | Captured from the tagged Java test sources. |

The tool names, input schemas, action flags, panel assignments, and all 269 starter mappings remain unchanged. The route catalogue adds `basePath` to `/mappings/flat` and three sub-contracts under `GET /exceptions/{id}` for the exception group, its occurrences and each occurrence's binding diagnostics. DTO additions include `requestId`, `bindingDiagnostics`, and `bindingDiagnosticsTruncated` on exception occurrences and request-profile exceptions; `authorizations` and `baselineComparison` on request journals; and `virtualThreadPinningSupported`, `pinnedEvents`, `outsidePinnedEvents`, and `pinnedDurationMicros` on the resource profile. BootUI also adds the `route-latency-outliers` insight kind. The source definitions are in `BootUiApiContractCatalog.java`, `MappingsReport.java`, `RequestProfileExceptionDto.java`, and `RouteLatencyOutliers.java`.

## Status changes

Route status remains grounded in the 2.3.0 live goldens. `/mappings/flat` changes from matched to partial against the 2.5.0 static contract because that contract now requires `basePath`; its 2.3.0 live payload still matches. The route counts change from 5 matched / 28 partial / 33 missing / 30 n-a to 4 / 29 / 33 / 30. The route matched-count pin is 4 until A2 adds `basePath`.

The property status adds three missing rows because sharpit has no corresponding setting fields. `scan-timeout` is tracked in A5, the request-ID header property is tracked in A8, and instance discovery is outside this release because its lease-file behavior conflicts with the host application's no-write startup rule. The property counts change from 103 matched / 11 partial / 95 missing to 103 / 11 / 98.

The citation inventory test records the 120 unique `# ported:` class/method citations that are not present in the 2.5.0 inventory in `tests/test_ported_citations.py`. These citations remain visible for follow-up; none is removed silently.

The 2.5.0 live golden capture remains deferred until BootUI runs in the reference application with its databases.
