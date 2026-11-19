# G1 — Agent playbooks and AI-agents guide

Production path: `skills/sharpit/references/playbooks/`, `skills/sharpit/SKILL.md`, `plugins/sharpit/skills/sharpit/`, `website/docs/ai-agents.md`.

| Scenario | Expected behaviour |
|---|---|
| Agent seeks guidance on general health, DB, slow route, errors, verification, or Python performance | Targeted playbook loaded from `skills/sharpit/references/playbooks/` with exact sharpit tools and commands |
| Agent connects via MCP or CLI | `website/docs/ai-agents.md` guides setup, recipes, bounds, and review-first authorization |
| Tool or CLI command cited in playbook/guide | Validated against `sharpit.engine.tools.TOOLS` and `sharpit.cli.commands` parser |
| Shipped plugin references tree | Identical byte-for-byte to `skills/sharpit/references/` tree |
| BootUI capability has no sharpit port (e.g. JVM/JFR heap dump, Java agent probes) | Documented as limitation in playbook; recorded as partial/n-a in matrix fragment |

- [x] **Step 1:** Create `skills/sharpit/references/playbooks/README.md` with shared contract, authorization, budget, and reporting.
- [x] **Step 2:** Port five core playbooks (`application-checkup.md`, `database-efficiency.md`, `slow-endpoint.md`, `errors-and-hidden-failures.md`, `verify-my-changes.md`) with sharpit tools and `sharpit` commands.
- [x] **Step 3:** Write `python-performance-and-memory.md` covering real sharpit evidence (threads, SQL timing, request profile, process info), explicitly stating limitations where BootUI had JVM-specific tools.
- [x] **Step 4:** Port `website/docs/ai-agents.md` from BootUI's `docs/AI-AGENTS.md` and add it to `website/mkdocs.yml` navigation.
- [x] **Step 5:** Add "Playbooks" section to `skills/sharpit/SKILL.md`, copy `SKILL.md` and `references/` tree to `plugins/sharpit/skills/sharpit/`, update root `README.md` with one line pointing agents to playbooks.
- [x] **Step 6:** Add test for plugin references tree parity in `tests/test_agent_plugin.py`, and test in `tests/docs/` that all MCP tool names and `sharpit ...` commands cited in playbooks/guide exist and parse.
- [x] **Step 7:** Create matrix fragment `docs/reference/matrix-updates/g1-playbooks.tsv` recording matched, partial, and n-a rows.
- [x] **Step 8:** Run all gates (`tests/docs`, `tests/test_agent_workflow.py`, `tests/test_agent_plugin.py`, `tests/cli`, `tests/parity`, `tests/test_lazy_package.py`, `ruff`, `pyright`, `mkdocs build`), commit and report.
