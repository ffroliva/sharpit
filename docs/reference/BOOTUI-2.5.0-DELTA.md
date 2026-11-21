# BootUI 2.4.0 to 2.5.0 static fixture delta

The static capture uses BootUI tag `v2.5.0` at commit `c4458db8dd18c08074119f22a79dda3e714abbda`. The fixtures are generated with `scripts/capture_bootui.py --version 2.5.0` from the BootUI source tree.

## Captured fixture changes

| Fixture | BootUI 2.4.0 | BootUI 2.5.0 | Source or reason |
|---|---:|---:|---|
| Panels | 65 | 65 | `BootUiPanels.java`; the panel catalogue is unchanged. |
| Tools | 116 | 116 | `bootui-cli/src/main/resources/bootui-tools.json`; A2 ports the `get_mappings` and `get_request_profile` descriptions. Authorization evidence remains tracked in B4. |
| Route contracts | 82 reads, 78 actions, 269 starter mappings | 85 reads, 78 actions, 269 starter mappings | `BootUiApiContractCatalog.java`; the three added reads describe exception occurrences and their binding diagnostics. |
| Properties | 209 | 212 | `BootUiProperties.java`; adds `bootui.vulnerabilities.scan-timeout=60s`, `bootui.http-exchanges.expose-request-id-header=true`, and `bootui.cli.instances-dir` with no default. |
| Rule identifiers | 604 | 688 | Rule registries and `RestApiRules.java`; the captured union increases by 84. `rule-ids-diff.json` records 0 documentation-only and 32 Java-only identifiers. |
| Test inventory | 1,128 classes, 10,927 methods | 1,144 classes, 11,204 methods | Captured from the tagged Java test sources. |

The tool names, input schemas, action flags, panel assignments, and all 269 starter mappings remain unchanged. The route catalogue adds `basePath` to `/mappings/flat` and three sub-contracts under `GET /exceptions/{id}` for the exception group, its occurrences and each occurrence's binding diagnostics. DTO additions include `requestId`, `bindingDiagnostics`, and `bindingDiagnosticsTruncated` on exception occurrences and request-profile exceptions; `authorizations` and `baselineComparison` on request journals; and `virtualThreadPinningSupported`, `pinnedEvents`, `outsidePinnedEvents`, and `pinnedDurationMicros` on the resource profile. BootUI also adds the `route-latency-outliers` insight kind. The source definitions are in `BootUiApiContractCatalog.java`, `MappingsReport.java`, `RequestProfileExceptionDto.java`, and `RouteLatencyOutliers.java`.

## Status changes

Route status remains grounded in the 2.3.0 live goldens. A2 adds `basePath` to `/mappings/flat`, so the route matches both the 2.3.0 payload shape and the 2.5.0 static contract. The route counts are 5 matched / 28 partial / 33 missing / 30 n-a, and the matched-count pin is 5.

The property status adds three missing rows because sharpit has no corresponding setting fields. `scan-timeout` is tracked in A5, the request-ID header property is tracked in A8, and instance discovery is outside this release because its lease-file behavior conflicts with the host application's no-write startup rule. The property counts change from 103 matched / 11 partial / 95 missing to 103 / 11 / 98.

The citation inventory test records 120 unique class/method citations and 83 unqualified `# ported:` labels that cannot be resolved against the 2.5.0 inventory in `tests/test_ported_citations.py`. These citations remain listed for follow-up; none is removed silently.

The 2.5.0 live golden capture remains deferred until BootUI runs in the reference application with its databases.

## Commit classification

Each commit in `v2.4.0..v2.5.0` is classified by its Python applicability and 0.8.0 lane. Merge commits carry no independent feature change.

| Commit | PR | Subject | Area | Classification |
|---|---:|---|---|---|
| `c4458db8d` | — | Release v2.5.0 | integration/build | docs/build only |
| `712ef9f81` | — | docs: finalize 2.5.0 release notes | docs | docs/build only |
| `29aa852f2` | #1728 | Bump io.quarkiverse.langchain4j:quarkus-langchain4j-bom from 1.14.2 to 1.15.0 (#1728) | Bump io.quarkiverse.langchain4j | docs/build only |
| `31d1d7878` | #1721 | Bump jsdom from 30.1.3 to 31.0.0 in /bootui-ui/src/main/frontend (#1721) | integration/build | docs/build only |
| `fe70c1e5d` | #1724 | Bump vite-plugin-checker in /bootui-ui/src/main/frontend (#1724) | integration/build | docs/build only |
| `621944d0f` | #1730 | Fix Windows cleanup of ArchUnit import test JAR (#1730) | integration/build | docs/build only |
| `67655b876` | #1716 | Bump github/gh-aw-actions/setup from 1.0.1 to 1.2.1 (#1716) | integration/build | docs/build only |
| `b62090f4c` | #1723 | Bump sass-embedded from 1.107.1 to 1.108.1 (#1723) | integration/build | docs/build only |
| `8aa51012c` | #1725 | Bump org.codehaus.mojo:flatten-maven-plugin from 1.8.0 to 1.9.0 (#1725) | Bump org.codehaus.mojo | docs/build only |
| `e8b3e352b` | #1729 | Bump Quarkus LTS to 3.40.1.2 (#1729) | integration/build | n-a: Quarkus LTS baseline applies to the Java runtime |
| `264b81512` | #1722 | Bump @playwright/test (#1722) | integration/build | docs/build only |
| `3cc7cb618` | #1727 | Bump org.codehaus.mojo:build-helper-maven-plugin from 3.6.2 to 3.8.0 (#1727) | Bump org.codehaus.mojo | docs/build only |
| `d1b9dc1e9` | #1717 | Bump the vue group in /bootui-ui/src/main/frontend with 2 updates (#1717) | integration/build | docs/build only |
| `0f1715ca3` | #1718 | Bump @playwright/test (#1718) | integration/build | docs/build only |
| `c2d0b9482` | #1719 | Bump vue from 3.5.44 to 3.5.45 in the vuepress group across 1 directory (#1719) | integration/build | docs/build only |
| `1f5b25ed8` | #1720 | Bump serve from 14.2.6 to 14.2.7 (#1720) | integration/build | docs/build only |
| `e8524c7c6` | #1714 | Prepare 2.5.0 release notes and refresh documentation screenshots (#1714) | integration/build | docs/build only |
| `464562d90` | — | Prepare 2.5.0 release notes and refresh documentation screenshots | integration/build | docs/build only |
| `c917685c2` | #1713 | Make button-shaped links recognizable with chain-link icons (#1713) | integration/build | UI (A7) |
| `3d35a0a05` | #1712 | Improve Runtime Insights and Live Activity request profile UI (#1712) | integration/build | UI (A7) |
| `6dd30975c` | #1711 | Open HTTP route exchanges in a responsive drawer (#1711) | integration/build | UI (A7) |
| `e5c90feec` | — | Improve Runtime Insights and Live Activity request profile UI | integration/build | docs/build only |
| `456da138b` | — | Open HTTP route exchanges in a responsive drawer | integration/build | docs/build only |
| `9d7996007` | #1688 | Add intra-route baseline comparison to Request Profile (#1688) | integration/build | n-a: request-journal baseline route is not implemented |
| `9f7cad7c7` | — | Merge origin/main and add Slow route outlier seed to Spring sample app | integration/build | docs/build only |
| `1108c050e` | #1677 | Live Activity & Request Profile: surface per-request authorization decisions and timeline entries (#1677) | Live Activity & Request Profile | n-a: authorization journal source is deferred |
| `aa4fa5dca` | #1670 | Merge branch 'main' and update Runtime Insights check count to 29 (#1670) | integration/build | ported in 0.8.0 (A3) |
| `f30cb7f5d` | #1710 | Reduce release payload size and restore 20 MB budget (#1710) | integration/build | n-a: Spring, Hibernate, Quarkus, JVM or BootUI build-specific change |
| `4ab608260` | #1708 | Pentesting Advisor: add 6 OWASP 2025 checks (PT-A02-007/008, PT-A05-073, PT-A07-008, PT-A08-001, PT-A10-001) (#1708) | Pentesting Advisor | n-a: Spring, Hibernate, Quarkus, JVM or BootUI build-specific change |
| `72cfa6662` | — | Merge remote-tracking branch 'origin/main' into jdubois-issue-1669-request-authz-activity | integration/build | docs/build only |
| `fb98d19ad` | #1675 | Add loopback-gated X-BootUI-Request-Id response header and UI filter tip (#1675) | integration/build | ported in 0.8.0 (A8) |
| `933af66e8` | #1679 | Exceptions: extract per-occurrence 400/422 validation & binding diagnostics and scrub rejected values (#1679) | Exceptions | ported in 0.8.0 (A4a/A4b) |
| `ba46c05d7` | — | Merge remote-tracking branch 'origin/main' into jdubois-issue-1669-request-authz-activity | integration/build | docs/build only |
| `a3232971a` | — | Merge branch 'main' into jdubois-http-exchanges-request-id-header | integration/build | docs/build only |
| `663efeb50` | #1706 | Hibernate Advisor: add HIB-MAP-025/027, HIB-ENTITY-011/012, HIB-FETCH-009, HIB-QUERY-009, and HIB-CACHE-004 (#1706) | Hibernate Advisor | n-a: Spring, Hibernate, Quarkus, JVM or BootUI build-specific change |
| `443c0121c` | #1687 | Add bootui init and handshake-verified local instance discovery (#1673) (#1687) | integration/build | n-a: local instance discovery writes a host lease file, which violates the no-write startup constraint |
| `2f04a8599` | #1709 | Security Advisor: add 6 WebFlux parity rules and 4 Quarkus Security rules (#1709) | Security Advisor | n-a: Spring, Hibernate, Quarkus, JVM or BootUI build-specific change |
| `a334469e0` | #1700 | Fix Spring CI evidence collection and diagnostics (#1700) | integration/build | n-a: Spring CI evidence collection requires the Java build and Spring sample |
| `ac2afb3e7` | #1702 | Pentesting Advisor: retire 13 duplicate and noisy checks (#1658) (#1702) | Pentesting Advisor | n-a: Spring, Hibernate, Quarkus, JVM or BootUI build-specific change |
| `6f9e02724` | — | Merge remote-tracking branch 'origin/main' into jdubois-exceptions-binding-diagnostics | integration/build | docs/build only |
| `9c934b47c` | #1707 | Memory Advisor: add MEM-FOOTPRINT-005 (cgroup v2 throttling/OOM), MEM-CONTENT-005 (ClassLoader/proxy bloat), and MEM-GC-009 (external System.gc) (#1707) | Memory Advisor | n-a: Spring, Hibernate, Quarkus, JVM or BootUI build-specific change |
| `c0356de3b` | #1703 | Vulnerabilities Advisor: add cross-branch EOL fix verification, complete-census SBOM reconciliation, and whole-scan deadline budget (#1703) | Vulnerabilities Advisor | ported in 0.8.0 (A5) |
| `0c49bde20` | #1705 | Database Advisor: add 11 schema, dialect, JPA, driver, pool, and server rules (#1705) | Database Advisor | missing (next release) |
| `158ea9fbf` | #1704 | Security Advisor: retire SEC-HEAD-010, SEC-SESSION-007, SEC-CONFIG-005, QS-TLS-002, and SEC-ACT-004 (#1704) | Security Advisor | ported in 0.8.0 (A1) |
| `8cb269adb` | #1696 | Spring Advisor: add SPRING-WIRING-010/011 and SPRING-PERF-008/009/011 rules (#1696) | Spring Advisor | n-a: Spring, Hibernate, Quarkus, JVM or BootUI build-specific change |
| `e41fdf221` | #1697 | Add startup compatibility diagnostics and safe upgrade policy (#1697) | integration/build | n-a: BootUI startup compatibility checks inspect Java runtime and framework versions |
| `d9e8134cd` | #1698 | Quarkus Advisor: add 10 rules across ArC CDI, virtual threads, worker pools, config hygiene, Agroal, and HTTP limits (#1698) | Quarkus Advisor | n-a: Spring, Hibernate, Quarkus, JVM or BootUI build-specific change |
| `64317e684` | #1699 | Memory Advisor: retire MEM-HEAP-008, MEM-POOL-007, MEM-CLASS-002, and MEM-THREAD-004 (#1699) | Memory Advisor | n-a: Spring, Hibernate, Quarkus, JVM or BootUI build-specific change |
| `9ca093f76` | #1694 | Architecture Advisor: add ARCH-SPRING-027, ARCH-SPRING-031, and ARCH-CODE-019 (#1694) | Architecture Advisor | n-a: Spring rules require Java bean metadata; ARCH-CODE-019 checks JDK shared fields |
| `8ad0849ac` | #1689 | REST API Advisor: add RAPI-MAP-012, RAPI-MAP-013, RAPI-VALID-007, RAPI-VER-008, and RAPI-PAGE-004 (#1689) | REST API Advisor | missing (next release) |
| `5e1e0f50f` | — | Merge branch 'main' into jdubois-http-exchanges-request-id-header | integration/build | docs/build only |
| `3278a7ee1` | — | Merge remote-tracking branch 'origin/main' into jdubois-exceptions-binding-diagnostics | integration/build | docs/build only |
| `787f61960` | #1676 | HTTP Probe: add route picker from Mappings, base-path composition, and Open in HTTP Probe prefill (#1676) | HTTP Probe | ported in 0.8.0 (A2) |
| `ae9fb7631` | — | Budget Maven publications for three monthly releases | integration/build | docs/build only |
| `1668f7c87` | #1693 | Hibernate Advisor: retire HIB-CONFIG-011, HIB-CONFIG-007, and HIB-QUERY-006 (#1693) | Hibernate Advisor | n-a: Spring, Hibernate, Quarkus, JVM or BootUI build-specific change |
| `ec9bd1090` | #1670 | Add route-latency-outliers Runtime Insights observation (#1670) | integration/build | ported in 0.8.0 (A3) |
| `8174457ea` | — | Surface X-BootUI-Request-Id hints in Live Activity and HTTP Probe | integration/build | docs/build only |
| `31ddb2373` | #1692 | Security Advisor: fix constantGrant authorization managers, Tomcat Jasper barrier, Actuator @Selector operations, and Quarkus {param} route handling (#1692) | Security Advisor | n-a: Spring Security, Tomcat and Quarkus route handling have no matching sharpit rule. |
| `842e64762` | #1695 | Database Advisor: retire DB-POOL-004, DB-SERVER-006, and DB-SERVER-002 (#1695) | Database Advisor | ported in 0.8.0 (A1) |
| `3e1c23bf4` | #1690 | Pentesting Advisor: fix BootUI CSRF chain exclusion, WebFlux firewall PARTIAL scan, Actuator health exemption, and JSON API 404 classification (#1690) | Pentesting Advisor | n-a: BootUI-specific CSRF chains, WebFlux firewall and Actuator checks have no matching sharpit rule. |
| `1378cdc11` | #1691 | Fix Vulnerabilities Advisor MAL- guidance, alias priority, host exclusion, and reach/PURL/withdrawal bugs (#1691) | Fix Vulnerabilities Advisor | ported in 0.8.0 (A5) |
| `1690e75d2` | — | Enable X-BootUI-Request-Id by default and add UI filter tip | integration/build | docs/build only |
| `51a2fe06c` | — | Merge branch 'main' into jdubois-request-profile-baseline-comparison | integration/build | docs/build only |
| `1f8664653` | — | Merge remote-tracking branch 'origin/main' into jdubois-exceptions-binding-diagnostics | integration/build | docs/build only |
| `2ce7614d8` | — | Merge branch 'main' into jdubois-http-exchanges-request-id-header | integration/build | docs/build only |
| `6e70d759c` | — | Merge remote-tracking branch 'origin/main' into jdubois-issue-1669-request-authz-activity | integration/build | docs/build only |
| `1ca6a3bb4` | — | Add startup compatibility diagnostics for BootUI | integration/build | docs/build only |
| `151008903` | #1686 | Memory Advisor: exclude BootUI-triggered Full GCs from MEM-GC-002/003/005/006 and fix -Xss, cgroup ancestor, and collection-usage handling (#1686) | Memory Advisor | n-a: JVM garbage-collector and cgroup memory accounting rules have no Python equivalent. |
| `6a1c56ac4` | — | Merge origin/main into jdubois-http-probe-route-picker-and-prefill | integration/build | docs/build only |
| `edadcd1e9` | #1685 | Runtime Insights JFR Profiler: attribute jdk.VirtualThreadPinned events to routes and frames (#1685) | Runtime Insights JFR Profiler | n-a: JFR virtual-thread pinning events are specific to the JVM |
| `468b7d083` | #1683 | Quarkus Advisor: retire QA-WEB-002 and fold zero/non-positive shutdown timeout into QA-WEB-004 (#1683) | Quarkus Advisor | n-a: Spring, Hibernate, Quarkus, JVM or BootUI build-specific change |
| `c89130c29` | #1670 | Address rubber-duck review findings for baseline comparison (#1670) | integration/build | ported in 0.8.0 (A3) |
| `c1010a6e7` | #1684 | Spring Advisor: retire SPRING-REACTIVE-001 and SPRING-WEB-003, and defer SPRING-MGMT-001/002/004 when application Security chains exist (#1684) | Spring Advisor | n-a: Spring, Hibernate, Quarkus, JVM or BootUI build-specific change |
| `feea3620f` | #1682 | Fix Database Advisor PostgreSQL serial types, DB-SCHEMA-005/DB-HIB-005, and catalog caps (#1682) | Fix Database Advisor | partial: ported here (DB-SCHEMA-005, PostgreSQL serial aliases, bounded/incomplete catalog handling); n-a: DB-HIB-005 datasource attribution requires an ORM-to-datasource binding that SQLAlchemy's supported mapping model does not expose; Oracle catalogs are not read |
| `b3d29c2b9` | #1681 | Hibernate Advisor: fix HIB-QUERY-004 derivedQueryVerified, HibernateQueryShape comma/alias parser, Quarkus profiles, and @Embedded expansion (#1681) | Hibernate Advisor | n-a: Hibernate query derivation and embedded mappings are Java ORM internals. |
| `6df84dfe2` | #1670 | Add intra-route baseline comparison to Request Profile (#1670) | integration/build | ported in 0.8.0 (A3) |
| `87b347218` | #1672 | Address rubber-duck review findings on JFR pinning attribution (#1672) | integration/build | n-a: Spring, Hibernate, Quarkus, JVM or BootUI build-specific change |
| `8538194a4` | #1680 | Architecture Advisor: retire obsolete ARCH-CODE-004 and ARCH-CODE-018 rules (#1680) | Architecture Advisor | ported in 0.8.0 (A1) |
| `20bffcaca` | #1672 | Attribute jdk.VirtualThreadPinned events in JFR resource profiler (#1672) | integration/build | n-a: Spring, Hibernate, Quarkus, JVM or BootUI build-specific change |
| `2add18cf6` | — | Address rubber-duck findings and Central bundle budget | integration/build | docs/build only |
| `8a33819ab` | — | Filter route picker options by query immediately and cancel stale focus fetch on input | integration/build | docs/build only |
| `300d13cbb` | #1678 | REST API Advisor: retire 8 noisy style and OpenAPI rules (RAPI-MAP-004, RAPI-NAME-002, RAPI-RESP-004/008, RAPI-VER-002/005, RAPI-DOC-001/002) (#1678) | REST API Advisor | ported in 0.8.0 (A1) |
| `fddb4de4b` | — | Address 3-model rubber-duck review findings on HTTP Probe route picker and prefill | integration/build | docs/build only |
| `93c1074ad` | — | Address rubber-duck review findings for authorization decisions | integration/build | docs/build only |
| `8c6955835` | — | Address 3-model rubber-duck review findings | integration/build | docs/build only |
| `52ae2b63f` | — | Extract per-occurrence 400/422 validation & binding diagnostics and scrub rejected values | integration/build | docs/build only |
| `60b56258e` | — | Surface per-request authorization decisions in Live Activity and request profiles | integration/build | docs/build only |
| `6e3cf8862` | — | Add HTTP Probe route picker from Mappings, base-path composition, and Open in HTTP Probe prefill | integration/build | docs/build only |
| `2be1c2665` | — | Add opt-in loopback-gated X-BootUI-Request-Id response header | integration/build | docs/build only |
| `8063e3069` | #1664 | Architecture Advisor: fix Kotlin suspend self-invocation, package cycle roots, and rule accuracy (#1664) | Architecture Advisor | partial: Python's existing package-cycle graph handles cross-root cycles over resolved package imports; n-a: configured Java package-slice roots, Kotlin suspend bytecode and JVM self-invocation behavior have no direct Python equivalent |
| `b9e6355c0` | #1662 | Quarkus Advisor: fix QA-WEB-001 BuildTime config ordinal, clean dev-mode scoring, namespace() parser, and CDI collector bugs (#1662) | Quarkus Advisor | n-a: Quarkus build-time configuration and CDI internals are not exposed by sharpit. |
| `1f6626c5d` | #1661 | Spring Advisor: fix DataSource proxy unwrapping, WebFlux configurer filter, lazy task executor inspection, and JDK 24 virtual-thread gating (#1661) | Spring Advisor | n-a: Spring DataSource and WebFlux internals are not exposed by sharpit. |
| `208db8143` | #1663 | Fix REST API Advisor model extraction and Declared Error Contract status (#1663) | Fix REST API Advisor | partial: ported here (FastAPI duplicate-route normalization); n-a: Spring/JAX-RS model extraction, framework-mapped exception inheritance and JVM error-contract providers do not map to FastAPI's explicit exception-handler registry |
| `31141e237` | #1660 | docs: refresh roadmap for BootUI 2.4 (#1660) | docs | docs/build only |
| `ac404cac0` | — | docs: refresh roadmap for BootUI 2.4 | docs | docs/build only |
| `684385951` | #1630 | Smoke test the checkout Action against the Spring sample (#1630) | integration/build | docs/build only |
| `f0705d247` | — | Smoke test the checkout Action against the Spring sample | integration/build | docs/build only |
| `21c306a01` | #1628 | Fix Action profile activation and improve CI diagnostics (#1628) | integration/build | n-a: Spring, Hibernate, Quarkus, JVM or BootUI build-specific change |
| `e22bcad98` | #1627 | Keep Maven releases below 20 MB (#1627) | integration/build | n-a: Spring, Hibernate, Quarkus, JVM or BootUI build-specific change |
| `a3c9e7ce9` | — | Keep Maven releases below 20 MB | integration/build | docs/build only |
| `cea39a71e` | — | docs: refresh 2.4.0 workshop and CLI references | docs | docs/build only |
