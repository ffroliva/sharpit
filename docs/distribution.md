# Distribution channels

Where people can install or discover sharpit, and where each channel stands. Every row carries the date it was
last checked. Do not update a row from memory; re-check it or mark it stale.

**Status:** `listed` · `submitted` (sent, awaiting review) · `todo` (eligible, not sent) · `blocked` (cannot proceed,
reason given) · `not eligible` (the channel's rules exclude us) · `closed` (the channel takes nothing) · `not listed`
(a crawler channel with no entry yet).

Outreach is the owner's call: a submission to a third party waits for an explicit go-ahead.

## Ledger

| Channel | Submit via | Status | URL | Checked |
|---|---|---|---|---|
| Agent plugin (Claude Code, Cursor, Codex marketplaces) | self-hosted in this repo (`plugins/sharpit`) | listed; PR [#194](https://github.com/ffroliva/sharpit/pull/194) merged 2026-11-16; `claude plugin validate .` passes | https://github.com/ffroliva/sharpit/tree/main/plugins/sharpit | 2026-11-16 |
| punkpeye/awesome-mcp-servers | PR | submitted, open; only a bot comment, asking for a Glama quality score (see Glama) | https://github.com/punkpeye/awesome-mcp-servers/pull/19620 | 2026-11-16 |
| ComposioHQ/awesome-claude-skills | PR | **blocked**: the repo limits PRs to collaborators (below). Branch is on the fork | https://github.com/ffroliva/awesome-claude-skills/tree/add-sharpit | 2026-11-16 |
| cursor.directory | web form (Manual tab) | submitted 2026-11-16, security scan pending, plugin hidden until it finishes | https://cursor.directory/plugins/sharpit | 2026-11-16 |
| hesreallyhim/awesome-claude-code | issue form | **blocked**: the repo limits new issues to collaborators (below) | https://github.com/hesreallyhim/awesome-claude-code | 2026-11-16 |
| travisvn/awesome-claude-skills | PR | **not eligible**: under 10 stars, no AI-assisted PRs (below) | https://github.com/travisvn/awesome-claude-skills | 2026-11-16 |
| PulseMCP | web form | **closed**: submissions paused since 2026-09-03 | https://www.pulsemcp.com/submit | 2026-11-16 |
| mcp.so | web form | **blocked**: only a $39 paid submission (below) | https://mcp.so/submit | 2026-11-16 |
| Glama | web form | listed, owned by ffroliva; **blocked** on the build test (below) | https://glama.ai/mcp/servers/ffroliva/sharpit | 2026-11-16 |
| Official MCP Registry | `mcp-publisher` | **blocked** (below) | https://registry.modelcontextprotocol.io | 2026-11-16 |
| Smithery | hosted or stdio server | **blocked** (below) | https://smithery.ai | 2026-11-16 |
| skills.sh | crawls on its own | not listed (page answers 404) | https://skills.sh/ffroliva/sharpit | 2026-11-16 |
| MCP Market | crawls on its own | not listed (page answers 404) | https://mcpmarket.com/server/sharpit | 2026-11-16 |
| claudemarketplaces.com | crawls on its own | not listed (a search for sharpit finds nothing) | https://claudemarketplaces.com | 2026-11-16 |

## Blocked, with the reason

- **ComposioHQ/awesome-claude-skills.** The entry is written (Development & Code Tools, alphabetical, between
  Septim Agents Pack and Skill Creator) and pushed to the fork, branch `add-sharpit`. `gh pr create` and the REST call
  refused it; the web compare page says "An owner of this repository has limited the ability to open a pull request to
  users that are collaborators on this repository." That is a repo setting, so only a maintainer can lift it. Earlier
  PR [#1905](https://github.com/ComposioHQ/awesome-claude-skills/pull/1905) predates it. Option: open an issue asking.
- **hesreallyhim/awesome-claude-code.** The issue form (https://github.com/hesreallyhim/awesome-claude-code/issues/new?template=recommend-resource.yml)
  opens with "An owner of this repository has limited the ability to create an issue to users that are collaborators on
  this repository", checked signed in as ffroliva on 2026-11-16. A repo setting; only a maintainer can lift it. Their
  CONTRIBUTING also says a recommendation must come from a human through that form, never `gh`. sharpit meets their
  eligibility (first commit 2026-10-30, active).
- **travisvn/awesome-claude-skills.** A skill under 10 stars is closed automatically (sharpit has 3), and a PR
  "explicitly generated / submitted with AI-assistance" is closed without comment. Revisit at 10 stars, with a
  human-written PR.
- **mcp.so.** The form has one button, "Pay and submit automatically" ($39). Spending is the owner's decision.
- **Glama build test.** The Dockerfile admin page (https://glama.ai/mcp/servers/ffroliva/sharpit/admin/dockerfile)
  reports the build test failed for lack of a start command. sharpit's MCP is HTTP inside the user's own app, so there
  is no process to start. Status only: no Dockerfile is guessed. Without a passing build there is no quality score, so
  PR #19620 cannot satisfy its bot.
- **Official MCP Registry and Smithery.** A registry needs a server it can start (stdio or a package). `server.json`
  declares only the `http://localhost:{port}/sharpit/api/mcp` remote, and `mcp-publisher validate` rejects a
  localhost remote. BootUI is in no public MCP registry either: it ships as plugins plus a CLI.
- **Stdio bridge `sharpit-mcp`.** The one change that would unblock Glama, the registry and Smithery. Out of scope
  here: it needs `/sharpit:predict` and `/sharpit:llm-council --tier high` before any code.

## Open questions for the owner

- **Crawlers and `skills/`.** No crawler lists sharpit yet, so nothing is published by mistake. They walk `skills/`,
  which holds maintainer workflows, not user skills; when one lists us, moving them to another directory or
  excluding them is a layout change that waits for the owner's answer.
- `glama.json` and `server.json` sit untracked at the repo root; they are not committed until the bridge decision.
