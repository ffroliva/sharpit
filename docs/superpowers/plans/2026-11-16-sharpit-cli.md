# sharpit command-line client implementation plan

**Goal:** `sharpit <command>` asks a running sharpit application one question from a terminal and prints the answer,
with the exit codes and `--fail-on` gates of BootUI 2.4.0's `bootui` command (issue #60).

**Architecture:** a new adapter package, `sharpit/cli/`, outside `engine/` and `fastapi/`. It never imports either. It
calls `POST {api}/cli/tools/{tool}` and `GET {api}/cli`, which already exist (`fastapi/routes/__init__.py`,
`_cli_routes`). Commands come from a committed manifest, `sharpit/cli/tools.json`, generated from
`sharpit.engine.tools.TOOLS` and guarded by a drift test, as BootUI generates `bootui-tools.json` from
`McpToolCatalog`. The only HTTP code is in one gatekeeper file, `sharpit/cli/client.py`. The package uses the standard
library only (`argparse`, `urllib.request`, `json`), so it adds no runtime dependency.

**Scenarios and required tests:** [2026-11-16-sharpit-cli-scenario.md](2026-11-16-sharpit-cli-scenario.md).

**Reference implementation:** BootUI v2.4.0, `bootui-cli/`: `BootUiCli`, `CliContext`, `ExitCodes`, `GlobalOptions`,
`CommandTree`, `FailOn`, `FailOnTools`, `TextRenderer`, `HelpListing`, `ToolManifest`, `BootUiClient`, `BootUiCatalog`,
and the tests `FailOnTests`, `BootUiClientTests`, `CommandTreeTests`, `TextRendererTests`, `ToolManifestGeneratorTests`.
Each task ports the classes it names and cites them with `# ported:`.

## Design decisions

1. The client has one HTTP gatekeeper file; `AGENTS.md` architecture rule 4 and `tests/engine/test_import_boundary.py`
   change in the same pull request.
2. The client makes no update request and has no `update` command.
3. `--token` takes precedence over `SHARPIT_TOKEN`, as in BootUI; the documentation recommends the environment variable.

## Scope

Included: the global options, one command per tool, `tools`, `mcp status|enable|disable`, `--fail-on`, exit codes
0 to 3, `--json`, `--version`, and the check that confirms a refusal came from sharpit.

Excluded, each recorded as a deviation from BootUI: `update`, `ci` (BootUI's assess, attach and check orchestration)
and `docs` (offline documentation).

## Global constraints (from AGENTS.md)

- Python `>=3.12`; runtime dependencies are exactly `starlette` and `packaging`. The client imports neither.
- `engine/` never imports `sharpit.cli`; `sharpit.cli` never imports `sharpit.fastapi`, `sharpit.pytest_plugin`,
  `fastapi` or `starlette`.
- `urllib.request` and `http.client` appear only in named gatekeeper files; this plan adds `sharpit/cli/client.py`.
- Secrets are masked before any output; the client never prints the token or the `Authorization` header.
- No module under `src/` exceeds 1000 lines; ruff C901 counts are pinned; ratchets only decrease.
- Each defect found becomes a regression test seen failing first (`scripts/dev/red_check.py` before each `test:` commit).
- Each ported test cites its BootUI source: `# ported: <Class>.<case>`.
- No AI attribution in commits or pull request bodies.

## Risk register

| Severity | Risk | Mitigation |
|---|---|---|
| Critical | A wrong target exits 2 and a CI gate reads it as "skip" (scenario 20) | Task 3 confirms through `GET {api}/cli` first |
| Critical | A redirect leaks the bearer token (1), or the token is printed in a message (3) | Task 2: redirects are not followed; the header never appears in a message |
| High | The gatekeeper change weakens the import boundary | Task 1 adds a planted-violation test for the new rule |
| High | Commands drift from the tool catalogue (9) | Task 4 drift test |
| High | Proxy environment variables route loopback calls through a proxy (10) | Task 2: direct opener |
| High | `--fail-on` semantics differ from BootUI or from the pytest plugin (#65) | Task 6 ports `FailOnTests` and compares with #65 |
| Medium | Start-up is slow, or a framework import breaks `--help` (16) | Task 7 import test |

## Tasks

### Task 1: Boundary rule and gatekeeper (tests first)
**Files:** `tests/engine/test_import_boundary.py`, `AGENTS.md` (architecture rule 4), `src/sharpit/cli/__init__.py`.
**Produces:** a rule that `sharpit/cli/client.py` is the only CLI module allowed to use `urllib.request`, and that
nothing under `engine/`, `fastapi/` or `pytest_plugin/` imports `sharpit.cli`.
- [ ] **Step 1:** Write the failing tests `test_only_the_cli_client_may_use_urllib_in_the_cli_package` and
      `test_nothing_outside_the_cli_imports_it`, each with a planted violation. They fail because the allow-list does not
      name `sharpit/cli/client.py` and the planted import is not flagged.
- [ ] **Step 2:** Change the allow-list and the rule text; run `red_check.py` on both node ids.
- [ ] **Step 3:** Commit `test: the CLI client is the one gatekeeper for its HTTP calls`.

### Task 2: HTTP client (gatekeeper)
**Files:** `src/sharpit/cli/client.py`, `tests/cli/test_client.py`.
**Produces:** `Client(options)` with `get(path)`, `invoke(tool, arguments)` and `catalog()`; raises `ClientError`.
- [ ] **Step 1:** Write failing tests:
      redirects are not followed and the token is not re-sent (scenario 1);
      configured proxies are ignored (`# ported: BootUiClientTests.directClientBypassesConfiguredHttpProxy`);
      duplicate keys and oversized bodies are rejected (`# ported: BootUiClientTests.boundedReadsRejectDuplicateKeysAndOversizedBodies`);
      `--timeout` bounds the whole read (`# ported: BootUiClientTests.boundedResponseBodyReadHonorsTheRemainingRequestTimeout`);
      `Authorization: Bearer` is sent only when a token is set, and no message or `repr` contains the token (scenarios 2, 3).
- [ ] **Step 2:** Implement with `urllib.request.build_opener(ProxyHandler({}), <redirect-refusing handler>)`, a byte cap,
      a strict JSON reader that rejects duplicate keys, and a `User-Agent`. Only this file's tests use a loopback server;
      every other CLI test injects a fake client factory (scenario 17).
- [ ] **Step 3:** Commit `feat: the sharpit CLI client talks to a running app over loopback`.

### Task 3: Outcomes and refusal confirmation
**Files:** `src/sharpit/cli/outcomes.py`, `src/sharpit/cli/exit_codes.py`, `tests/cli/test_outcomes.py`.
**Produces:** `ExitCodes` (0 success, 1 error, 2 refused, 3 threshold), `classify(status, body) -> Outcome`, and
`confirm_answered(client, result)`, ported from `CliContext.confirmBootUiAnswered`.
- [ ] **Step 1:** Write failing tests: a 403 from a target whose `GET {api}/cli` is not sharpit exits 1, not 2
      (scenario 20); a 503 with the catalogue `enabled: false` is a disabled endpoint (exit 2) and a plain 503 outage is
      exit 1; a read-only panel refusal is exit 2 with `PANEL_ACCESS_DENIED` (scenario 7;
      `# ported: BootUiClientTests.aToolIsReportedRefusedWhenItsPanelIsOffOrTheActionIsReadOnly`).
- [ ] **Step 2:** Implement against the status table of `engine/tool_dispatch.cli_invoke` (503 CLI disabled, 404 unknown
      or unavailable tool, 400 invalid, 429 capacity, 504 timeout, 500 other).
- [ ] **Step 3:** Commit `feat: a refusal is reported only after sharpit has answered`.

### Task 4: Manifest and drift test
**Files:** `scripts/dev/gen_cli_manifest.py`, `src/sharpit/cli/tools.json`, `src/sharpit/cli/manifest.py`,
`tests/cli/test_manifest.py`.
**Consumes:** `sharpit.engine.tools.TOOLS`. **Produces:** `Manifest.bundled()`.
- [ ] **Step 1:** Write failing tests: the checked-in manifest equals a fresh generation from `TOOLS`
      (`# ported: ToolManifestGeneratorTests`); command paths are unique and none is a prefix of another; each of the
      62 tools under BootUI's exact names keeps BootUI's command path from `tests/fixtures/bootui/2.3.0/tools.json`; the
      9 sharpit-only tools get a path chosen here and recorded in the deviation log.
- [ ] **Step 2:** Write the generator and generate the manifest. The client never imports `sharpit.engine` at run time.
- [ ] **Step 3:** Confirm that `tools.json` is included in the built wheel.
- [ ] **Step 4:** Commit `feat: the CLI commands are generated from the tool catalogue`.

### Task 5: Global options and command tree
**Files:** `src/sharpit/cli/options.py`, `src/sharpit/cli/commands.py`, `tests/cli/test_commands.py`.
**Produces:** `run(argv, environment, terminal, out, err, client_factory) -> int`, the in-process entry that BootUI's
`BootUiCli.run` provides; `main()` calls it with the real streams.
- [ ] **Step 1:** Write failing tests (`# ported: CommandTreeTests.<case>`): `--url`, `--api-path`, `--token`,
      `--timeout` (positive seconds), `--json`, `--no-color` and `--verbose` work before or after the command; `--token`
      takes precedence over `SHARPIT_TOKEN` (scenario 2); `SHARPIT_URL` and `SHARPIT_API_PATH` fill unset options; a bare
      `host:port` is accepted; `NO_COLOR` is honoured.
- [ ] **Step 2:** Build the `argparse` tree from the manifest: `-q/--query`, `-n/--limit`, `--id`, `--scan-id` and
      `--offset` only where the tool declares them; send only the arguments supplied.
- [ ] **Step 3:** Commit `feat: one sharpit command per tool, with BootUI's global options`.

### Task 6: `--fail-on`
**Files:** `src/sharpit/cli/fail_on.py`, `tests/cli/test_fail_on.py`.
- [ ] **Step 1:** Port every `FailOnTests` case, each with its `# ported:` line:
      `aFindingAtTheThresholdExitsThreeAndPrintsTheSameJson`, `aFindingAboveTheThresholdExitsThree`,
      `onlyLowerSeveritiesPass`, `theThresholdIsInclusiveAtEveryLevel`, `theValueIsCaseInsensitive`,
      `aReportWithNoFindingsPasses`, `severitiesOutsideTheOrderAreIgnored`, `aPartialScanWithAFindingStillFails`,
      `aPartialScanWithoutAFindingPassesButSaysItIsNotProof`, `anIgnoredSeverityWithFindingsIsNamedButDoesNotGate`,
      `zeroFindingsFromAScanWithNoUsableEvidenceCannotPass`,
      `aFindingStillFailsWhenTheEvidenceIsNotUsableAndUsableEvidencePasses`. A gate that cannot be evaluated exits 1.
- [ ] **Step 2:** Implement `evaluate` from `FailOn` and `FailOnTools`. The option is consumed by the client and is never
      sent as a tool argument. The insufficient-evidence gate on the insights list requests `query=all` when none is given.
- [ ] **Step 3:** Compare the semantics with #65 and state the result in the pull request.
- [ ] **Step 4:** Commit `feat: --fail-on gates on severity or insufficient evidence, as in BootUI`.

### Task 7: Output, `tools`, `mcp` and the entry point
**Files:** `src/sharpit/cli/render.py`, `src/sharpit/cli/__main__.py`, `pyproject.toml`
(`[project.scripts] sharpit = "sharpit.cli:main"`), `tests/cli/test_render.py`, `tests/cli/test_entry.py`.
- [ ] **Step 1:** Write failing tests: JSON by default when output is not a terminal and `--json` forces it
      (scenario 13); the tool's answer is printed verbatim before any gate reads it; a non-UTF-8 console never raises
      `UnicodeEncodeError` (scenario 14); `sharpit tools` lists what the target advertises, which takes precedence over the
      bundled manifest, and a tool the app does not advertise exits 1 naming it (scenario 8); `mcp enable|disable` is a
      panel action refused on a read-only panel with exit 2 (`# ported: TextRendererTests.<case>`).
- [ ] **Step 2:** `test_cli_imports_no_framework` imports the package in a subprocess with `fastapi` and `starlette`
      unavailable (scenario 16).
- [ ] **Step 3:** `test_cli_makes_no_update_check_request` asserts that the fake client receives exactly one request
      (scenario 15).
- [ ] **Step 4:** Commit `feat: the sharpit console script`.

### Task 8: Documentation and deviations
**Files:** `README.md`, `skills/sharpit/SKILL.md`, `CHANGELOG.md`, `docs/reference/PARITY.md`, the MVP design's
deviation log.
- [x] **Step 1:** Record the deviations: no `update`, `ci` or `docs`; no update check; `argparse` in place of picocli; the
      documented token recommendation; the nine sharpit-only command paths.
- [x] **Step 2:** Replace each statement that no command-line client exists (`CHANGELOG.md`, the skill, the MVP design's
      non-goals).
- [x] **Step 3:** Commit `docs: the sharpit command-line client`.

### Task 9: Live verification
- [ ] **Step 1:** Run `examples/fastapi_sample` with sharpit, then `sharpit tools`, `sharpit security scan --json`,
      `sharpit security scan --fail-on high`, a read-only refusal (exit 2), a wrong `--api-path` (exit 1), and the same
      commands with `HTTP_PROXY=http://127.0.0.1:9` set. Keep the output in the pull request description.
- [ ] **Step 2:** `/sharpit:check`, then `/sharpit:branch-review`.

## Definition of done

- [ ] All steps checked
- [ ] `/sharpit:check` passes (`ruff check`, `ruff format --check`, `pyright`, `pytest -q -n auto`)
- [ ] Every Critical and High scenario has a named test
- [ ] Deviations from BootUI are recorded in the design's deviation log
- [ ] Live verification output is in the pull request description
- [ ] The pull request lists each finding, its test and the failing output
