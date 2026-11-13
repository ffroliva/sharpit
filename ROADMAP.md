# Roadmap: how close sharpit is to BootUI

sharpit is a Python/FastAPI port of [BootUI](https://github.com/jdubois/boot-ui), the Spring Boot developer console.
Each sharpit release targets one BootUI tag: 0.6.0 targets BootUI 2.3.0, and 0.7.0 targets BootUI 2.4.0.

## Where it stands

| | sharpit 0.5.0 | sharpit 0.6.0 | BootUI 2.3.0 | BootUI 2.4.0 |
|---|---|---|---|---|
| MCP/CLI tools | 54 | 71 | 116 | 116 |
| Tools under BootUI's exact names | 45 | 62 | - | - |
| Panels | 31 | 48 (46 listed in the console) | 65 (Spring) | 65 (Spring) |
| Runtime insight kinds that evaluate | none | 8 of 28 registered | 28 | 28 |
| BootUI API routes served, of the 66 that apply to Python | not measured | 33 (5 shape-identical, 28 partial) | 66 | not captured |

`tests/docs/test_parity_matrix.py` recomputes the sharpit 0.6.0 and BootUI 2.3.0 columns from the code and the BootUI
2.3.0 fixtures on every run. The sharpit 0.5.0 column was counted at the `v0.5.0` tag, and the BootUI 2.4.0 column at
BootUI's `v2.4.0` tag, both on 2026-11-13; neither moves.

How each row is counted:

- **Tools:** sharpit's MCP/CLI tool catalogue (`sharpit.engine.tools.TOOLS`) against BootUI's
  (`tests/fixtures/bootui/2.3.0/tools.json`; at BootUI's tags, `bootui-cli/src/main/resources/bootui-tools.json`).
  "Exact names" counts the sharpit tools whose name is also a BootUI tool name.
- **Panels:** sharpit's panel registry, and the panels `GET /sharpit/api/panels` lists. BootUI's count is the Spring
  sample app's (the live 2.3.0 capture, `tests/fixtures/bootui/2.3.0/panels.json`; at BootUI's tags,
  `bootui-conformance/.../expected-panels-spring.json`). Some BootUI panels are Java-only, so 48 of 65 is not a
  percentage of the work left.
- **Runtime insights:** sharpit registers all 28 of BootUI's insight kinds; 8 are implemented and 20 are not yet. A
  kind evaluates when it is implemented and every journal source it requires is one sharpit produces (all 8 do).
  BootUI counts the classes implementing `Observation`.
- **Routes:** the BootUI 2.3.0 live goldens (`tests/parity/routes_23_status.json`): 96 routes, of which 30 are
  Java-only; of the other 66, 5 match BootUI's shape, 28 are served with known differences and 33 are not built yet.

## The 8 insight kinds that evaluate in 0.6.0

`ai-usage-by-route`, `connections-per-request`, `errors-behind-2xx`, `exception-hotspots`,
`framework-warnings-by-route`, `lazy-sql-after-handler`, `route-time-breakdown`, `safe-method-dml`.

## What is next (0.7.0, BootUI 2.4.0)

BootUI 2.4.0 has the same number of tools, panels and insight kinds as 2.3.0, so 0.7.0 is about behaviour, not new
panels:

- the 33 BootUI routes sharpit does not serve yet;
- the 20 insight kinds not implemented yet, and the journal sources most of them need (`orm`, `transaction`,
  `authorization`, `gc`, `app-event`, `resources`, `agent.executors`);
- what 2.4.0 changes inside existing features;
- the known limitations listed under 0.6.0 in [CHANGELOG.md](CHANGELOG.md).
