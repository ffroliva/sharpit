# Agent Plugins Implementation Plan

> For agentic workers: run `/sharpit:status --feature agent-plugins` for the next unchecked step. One task at a time;
> `/sharpit:check` before every commit.

**Goal:** a Claude Code user can run `/plugin marketplace add ffroliva/sharpit` then `/plugin install sharpit@sharpit`
and get the sharpit skill plus a pre-wired connection to the app's read-only MCP endpoint; a Cursor user can do the
same from the Cursor plugin marketplace.

**Architecture:** configuration and docs only, no code under `src/sharpit/`. Plugin files live at the repo root
(`.claude-plugin/`, `.cursor-plugin/`, `plugins/sharpit/`), outside the wheel (`pyproject.toml` packages
`src/sharpit/**` only). The plugin's `mcp.json` points at the local endpoint `http://127.0.0.1:8000/sharpit/api/mcp`
with a `SHARPIT_MCP_URL` override, exactly as BootUI's plugin points at `http://127.0.0.1:8080/bootui/api/mcp` with
`BOOTUI_MCP_URL`. The skill is `skills/sharpit/SKILL.md`, copied, with a test that keeps the copy identical.

**Predict verdict:** GO 8/10 (2026-11-15, one pass, personas written by one agent, not dispatched). The stdio bridge
`sharpit-mcp` is out of scope here: it is a new surface and goes through `/sharpit:predict` and
`/sharpit:llm-council --tier high` on its own.

## Global Constraints

- `src/sharpit/__init__.py` is the only version site: no `version` key in any plugin or marketplace file.
- Reads have no side effects, and MCP is off by default (`SHARPIT_MCP_ENABLED=OFF`): the plugin must never enable it,
  start a process or write a file on the user's behalf.
- Port BootUI, do not reinvent: read BootUI's plugin files at the pinned tag before writing ours (Task 1).
- No AI attribution in commits. Conventional prefixes, explicit `git add` paths.
- Runtime deps stay `starlette` and `packaging`. Nothing here adds a dependency.

## Risk register

| Severity | Risk | Mitigation |
|---|---|---|
| High | Claude Code or Cursor cannot talk to sharpit's POST-only Streamable HTTP subset, so the plugin installs but never connects | Task 5 live-verifies against the sample app before docs announce it; the README states the verified client versions only |
| High | A token or a non-loopback URL ends up in `mcp.json` and ships publicly | Task 2 test: URL host must be `127.0.0.1` or `localhost`, no `Authorization`, `headers` or `token` key; remote use documented as the user's own override |
| Medium | The plugin skill drifts from `skills/sharpit/SKILL.md` | Task 2 byte-equality test |
| Medium | The skill is stale: it says 0.5.0 and 50 read-only MCP tools while the repo is 0.6.0 and the README counts 71 tools | Task 3 corrects both from code, not memory |
| Medium | Users see "connection refused" because MCP is off by default or the app uses another port | The plugin README and the skill's first paragraph give the enable step and the `SHARPIT_MCP_URL` override |
| Low | A `version` key appears in plugin files and drifts from `__version__` | Task 2 test asserts no `version` key |
| Low | The README order test (`gflow-cli` proof checks) breaks when a section is added | Task 4 runs it first and adds the section where the test allows |

### Task 1: Recon BootUI's plugin files (no code)

**Files:** none changed; findings go in the PR body.
**Interfaces:** Produces the exact file set and key names for Claude Code and Cursor.
- [ ] **Step 1:** In a BootUI clone, read `.claude-plugin/marketplace.json`, `plugins/bootui/.claude-plugin/plugin.json`,
  `plugins/bootui/mcp.json`, `plugins/bootui/plugin.json`, `.cursor-plugin/marketplace.json` and
  `plugins/README.md` at the pinned tag (`git -C <clone> show v2.3.0:<path>`; fall back to current `main` if a path
  is missing at the tag and say so).
- [ ] **Step 2:** Write the file list and the keys that differ between the Claude and Cursor variants (BootUI's own
  `ClaudeCodePluginPayloadTests` and `AgentPluginPayloadTests` name what it asserts: read them).
- [ ] **Step 3:** Decide Cursor layout from that reading. If BootUI's Cursor plugin needs a directory Cursor reads from
  `main` of a public repo, copy its layout; otherwise stop and record the gap.

### Task 2: Plugin payload with its tests

**Files:** create `tests/test_agent_plugin.py`, `.claude-plugin/marketplace.json`, `plugins/sharpit/.claude-plugin/plugin.json`,
`plugins/sharpit/mcp.json`, `plugins/sharpit/skills/sharpit/SKILL.md` (copy of `skills/sharpit/SKILL.md`),
`plugins/sharpit/README.md`.
**Interfaces:** Produces the installable Claude Code plugin `sharpit@sharpit`. Consumes `skills/sharpit/SKILL.md`.
- [ ] **Step 1:** Write failing tests (ported shape: `# ported: ClaudeCodePluginPayloadTests.<case>`):
  `test_marketplace_lists_plugin_with_existing_source`, `test_plugin_json_has_name_description_license_repository`,
  `test_plugin_has_no_version_key` (expected failure: files missing, so assert on the file existing first so the red
  is the assertion, not a crash), `test_mcp_url_is_loopback`, `test_mcp_has_no_credentials`,
  `test_plugin_skill_equals_repo_skill`, `test_plugin_files_are_not_in_the_wheel` (reads `pyproject.toml` hatch config).
- [ ] **Step 2:** Run `uv run python scripts/dev/red_check.py tests/test_agent_plugin.py` and confirm each failure is the
  named assertion.
- [ ] **Step 3:** Create the files. `mcp.json`: `{"mcpServers":{"sharpit":{"type":"http","url":"${SHARPIT_MCP_URL:-http://127.0.0.1:8000/sharpit/api/mcp}"}}}`
  following Task 1's keys. `plugin.json` homepage points at `https://ffroliva.github.io/sharpit/mcp/`.
- [ ] **Step 4:** Tests green. Delete one control (change the URL host) and confirm `test_mcp_url_is_loopback` fails.
- [ ] **Step 5:** Commit `feat: Claude Code plugin marketplace with the sharpit skill and local MCP connection`.

### Task 3: Refresh the user-facing skill the plugin ships

**Files:** `skills/sharpit/SKILL.md`, `plugins/sharpit/skills/sharpit/SKILL.md`.
- [ ] **Step 1:** Failing test `test_skill_version_matches_package` (reads `sharpit.__version__`, expects the skill's
  "0.x.y" banner to match; red today: it says 0.5.0, the package is 0.6.0).
- [ ] **Step 2:** Count the MCP tools from code (`uv run python -c` over the registry in `engine/tools.py` and `tools04/`,
  split read versus action) and correct the "50 read-only tools" sentence.
- [ ] **Step 3:** Put the enable step and the `SHARPIT_MCP_URL` override first in the MCP section: MCP is off by
  default, the endpoint is POST only, remote agents need the bearer token.
- [ ] **Step 4:** Re-copy to the plugin; both tests green. Commit `docs: skill states the current version and tool count, and the MCP enable step first`.

### Task 4: Cursor plugin

**Files:** `.cursor-plugin/marketplace.json` and the Cursor plugin files Task 1 lists.
- [ ] **Step 1:** Tests mirroring Task 2 for the Cursor payload (`# ported: AgentPluginPayloadTests.<case>`), red first.
- [ ] **Step 2:** Create the files from Task 1's layout; same loopback and no-credentials tests cover them.
- [ ] **Step 3:** Commit `feat: Cursor plugin marketplace for the sharpit MCP connection`.

### Task 5: Live verification

**Files:** evidence note in the PR body; no repo change unless a client fails.
- [ ] **Step 1:** Run the sample app per `/sharpit:live-verify` with `SHARPIT_MCP_ENABLED=ON`; confirm
  `POST /sharpit/api/mcp` answers `initialize` and `tools/list` with curl.
- [ ] **Step 2:** In Claude Code: `/plugin marketplace add <worktree path>`, `/plugin install sharpit@sharpit`, then
  confirm `/mcp` shows sharpit connected and one read tool returns data. Record the Claude Code version.
- [ ] **Step 3:** Repeat in Cursor if installed. If a client cannot connect, record the exact error and keep that client
  out of the README; do not paper over it.
- [ ] **Step 4:** Confirm MCP off (`SHARPIT_MCP_ENABLED` unset) answers with the disabled message, not a crash.

### Task 6: Docs and changelog

**Files:** `README.md`, `website/docs/mcp.md`, `CHANGELOG.md`, `docs/README.md` if it indexes plugins.
- [ ] **Step 1:** Run the README order test first and note which sections it pins.
- [ ] **Step 2:** Add "Use with an AI agent" to the README (Claude Code commands, Cursor path, the enable step), only for
  clients Task 5 verified. Add the same to `website/docs/mcp.md`.
- [ ] **Step 3:** CHANGELOG entry under Unreleased. Log the choice of plugins over registry listings as a deviation row if
  spec §14 tracks distribution.
- [ ] **Step 4:** `/sharpit:doc-review`, then commit `docs: install sharpit as a Claude Code or Cursor plugin`.

### Task 7: Owner steps after merge (not agent work)

- [ ] Submit the plugin to cursor.directory (account needed).
- [ ] Remove the invalid root `server.json` (it fails `mcp-publisher validate`); keep `glama.json` and commit it.
- [ ] Update punkpeye/awesome-mcp-servers PR #19620 if the maintainers ask for changes.
- [ ] Decide on the stdio bridge `sharpit-mcp` (separate predict and council, as a separate package).

## Definition of done

- [ ] All steps checked
- [ ] `/sharpit:check` green (ruff check, ruff format --check, pyright strict, pytest)
- [ ] Every High risk above has a named test or a Task 5 evidence line
- [ ] No `version` key in any plugin file; `src/sharpit` untouched
- [ ] Deviations from BootUI logged in the spec §14
- [ ] `/sharpit:live-verify` evidence in the PR body
