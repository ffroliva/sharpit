# Scenarios: the `sharpit` command-line client

Failure scenarios and required tests for the command-line client described in
[the implementation plan](2026-11-16-sharpit-cli.md) (issue #60).

## Reference

The client follows `bootui-cli` in BootUI 2.4.0 (`ExitCodes`, `GlobalOptions`, `CliContext`, `BootUiClient`, `FailOn`).
Between BootUI 2.3.0 and 2.4.0 the tool list is unchanged; seven tool descriptions changed. The server side already exists
in sharpit: `GET {api}/cli` lists the tools and `POST {api}/cli/tools/{tool}` runs one (`fastapi/routes/__init__.py`,
`engine/tool_dispatch.py`). Access is decided by `engine/guard.py`.

## Coverage

| Dimension | Applies | Reason |
|---|---|---|
| D1 Fail-closed activation | yes | an inactive app answers 404 on every path; the client reports that, not a tool failure |
| D2 Access guard | yes | the client is a new caller of the guard chain |
| D3 Masking | yes | the client prints server output and must never print the token |
| D4 Contract parity | yes | exit codes, options and output rules follow BootUI 2.4.0 |
| D5 Introspection drift | no | the client reads no FastAPI internals |
| D6 No side effects on reads | yes | the rule concerns the server's reads; the client is a separate process whose purpose is a socket |
| D7 OSV and EPSS failures | no | no scan is added; scans run on the server |
| D8 Host application integration | yes | authentication middleware that redirects, reverse proxies, proxy environment variables |
| D9 Scale and limits | yes | response size and time limits |
| D10 MCP and CLI parity | yes | the purpose of the client |

## Worst-case trace

Input: `sharpit --url http://localhost:8000 security scan`, run on the same machine.

1. The client connects from `127.0.0.1`. In `decide_guard` (`engine/guard.py`) `facts.peer` is `127.0.0.1` and no
   `forwarded`, `x-forwarded-for` or `x-real-ip` header is present, so `is_trusted_source` returns true.
2. `Host: localhost:8000` gives the request host `localhost`, which is in `_BUILT_IN_ALLOWED_HOSTS`. The Host check passes.
3. The client sends no `Sec-Fetch-Site` and no `Origin`, so `_is_blank(origin)` is true and `_is_cross_site` returns
   `False`. A client that copied a browser's `Origin` header would be refused, so it must send none.
4. `facts.api_sub_path` is set and the source is trusted, so the token check is skipped.
5. `_panel_access` checks the global and per-panel read-only settings for a POST. A read-only `security` panel returns
   `Denial(403, {"error": PANEL_ACCESS_DENIED, ...})`. The client reports this as a refusal (exit code 2).
6. `cli_tool` reads at most `mcp_max_payload_bytes` and calls `cli_invoke`: `cli_enabled` false returns 503 with
   `CLI_DISABLED_MESSAGE`; an unknown or unavailable tool returns 404; invalid parameters 400; capacity 429; timeout 504.

Result: on loopback the client needs no token and gains no access beyond the guard's. The statuses it must classify are
all defined.

## Scenario table

Severity: Critical (secret leak, a gate that passes wrongly, a read-side effect) · High (feature broken) ·
Medium (degraded, explicit error) · Low (cosmetic).

| # | Dim | Scenario | Severity | Expected behaviour | Test |
|---|---|---|---|---|---|
| 1 | D2 | The request carries a bearer token and the target redirects (for example authentication middleware answering 302) | Critical | redirects are not followed, so the token is not re-sent; exit 1 with a message naming the redirect | Integration |
| 2 | D2/D3 | A token passed as `--token` appears in process listings and shell history | High | the order is `--token`, then `SHARPIT_TOKEN`, as in BootUI; the documentation recommends the environment variable; the token is never printed, including with `--verbose` | Unit |
| 3 | D3 | `--verbose` or an error path prints request headers | Critical | the `Authorization` header is never printed | Unit |
| 4 | D2 | The target is not loopback and the Host allow-list refuses | High | the server's refusal text is shown with the name of the setting to change; exit 1 | Integration |
| 5 | D2 | The app is behind a reverse proxy, so forwarded headers make the caller untrusted | High | the token is required; a 401 prints the guard's challenge text; exit 1 | Integration |
| 6 | D1 | The app is inactive and every path returns 404 | High | exit 1 with a message that sharpit is not active at this URL; no traceback | Integration |
| 7 | D10 | An action tool targets a read-only panel | High | exit 2, distinct from exit 1, so scripts can tell a configuration statement from a failure | Integration |
| 8 | D10 | The client's catalogue lists a tool the app does not advertise (version skew) | High | exit 1 naming the tool; no silent success | Integration |
| 9 | D10 | A tool is added to the catalogue without a command | High | a test fails (BootUI: `ToolManifestGeneratorTests`) | Unit |
| 10 | D8 | `HTTP_PROXY` is set and `NO_PROXY` does not list `localhost` | High | the client connects directly and ignores configured proxies (BootUI: `BootUiClientTests.directClientBypassesConfiguredHttpProxy`) | Integration |
| 11 | D4 | `--fail-on high` against a `PARTIAL` scan | High | exit 0 with a note on stderr; exit 1 when the evidence is unusable and nothing is found; exit 3 when a finding meets the threshold (BootUI `docs/CLI.md`); consistent with #65 | Unit |
| 12 | D9 | The server returns a very large body, or does not answer | Medium | reads are capped and `--timeout` applies; exit 1 naming the flag to raise | Unit |
| 13 | D4 | Standard output is not a terminal | Medium | JSON is the default when piped, `--json` forces it, `NO_COLOR` is honoured | Unit |
| 14 | D4 | A Windows console with a non-UTF-8 code page receives non-ASCII text | Medium | no `UnicodeEncodeError` | Unit (Windows) |
| 15 | D6 | An update check at start-up (BootUI has `UpdateCheck`) | High | not implemented: the client makes no request beyond the one asked for | Unit |
| 16 | D6 | Importing the client pulls in `fastapi`, `starlette` or `sharpit.fastapi` | High | no framework import; `--help` works with only the runtime dependencies | Unit |
| 17 | D2 | Client tests open real sockets | Medium | the HTTP call goes through one injected seam; only the client's own tests use a loopback server | Unit |
| 18 | D3 | An error body contains text the server did not mask | Medium | the client prints only the server's error text and adds nothing from the request | Unit |
| 19 | D4 | Documentation still states that no command-line client exists (`skills/sharpit/SKILL.md`, `CHANGELOG.md`, the MVP design) | Low | updated in the same change | Documentation |
| 20 | D2 | `--url` points at another application, or `--api-path` is mistyped, and that application answers 403, 404 or 503 | Critical | the client does not exit 2 until `GET {api}/cli` shows that sharpit answered; otherwise exit 1 naming the target. Exit 2 is read as "skip" by CI gates, so a wrong target would pass (BootUI `CliContext.confirmBootUiAnswered`) | Integration |
| 21 | D9 | A response contains duplicate JSON keys or exceeds the size cap | High | rejected with exit 1; nothing is printed partially (BootUI `BootUiClientTests.boundedReadsRejectDuplicateKeysAndOversizedBodies`) | Unit |

## Required tests before merge (Critical and High)

- `test_cli_does_not_follow_a_redirect_with_the_token` (1)
- `test_cli_token_flag_wins_over_environment_like_bootui` (2)
- `test_cli_never_prints_the_authorization_header` (3)
- `test_cli_surfaces_host_refusal_with_setting_name` (4)
- `test_cli_reports_inactive_app_without_a_traceback` (6)
- `test_cli_exits_2_when_a_read_only_panel_refuses_an_action` (7)
- `test_cli_exits_1_naming_a_tool_the_app_does_not_advertise` (8)
- `test_cli_commands_match_the_tool_catalogue` (9)
- `test_cli_client_ignores_configured_proxies` (10), `# ported: BootUiClientTests.directClientBypassesConfiguredHttpProxy`
- `test_fail_on_exit_codes_match_bootui` (11), ported from `FailOnTests`, each case with its `# ported:` line
- `test_cli_makes_no_update_check_request` (15)
- `test_cli_imports_no_framework` (16)
- `test_cli_does_not_report_refused_until_the_catalog_confirms_sharpit_answered` (20), `# ported: CliContext.confirmBootUiAnswered`
- `test_cli_rejects_duplicate_keys_and_oversized_bodies` (21), `# ported: BootUiClientTests.boundedReadsRejectDuplicateKeysAndOversizedBodies`

## Deferred (Medium and Low)

Scenarios 12, 13, 14, 17 and 18 are tracked as follow-up issues; 19 is part of the change.

## Related issues

- #65 (a passing run exits 1 when an advisor can only partly assess the app) belongs to the same class as scenario 11.
  The client and the pytest plugin must agree on what a partly assessed result means.

## Design decisions

1. **One HTTP gatekeeper for the client.** `sharpit/cli/client.py` is the only client module that may use
   `urllib.request`. Rationale: the client must reach the application over HTTP, and the repository allows network
   libraries only in named files. Consequence: architecture rule 4 and `tests/engine/test_import_boundary.py` change in
   the same pull request, with a planted-violation test for the new rule.
2. **No update check.** The client sends no request other than the one the user asked for. Rationale: a background request
   on every command adds latency and failure modes in CI and falls outside the network rule in the safety model. Python
   packages are upgraded by their package manager. An explicit `sharpit update --check` may be added later.
3. **Token precedence follows BootUI.** `--token` takes precedence over `SHARPIT_TOKEN`. Rationale: identical behaviour to
   the reference. The documentation recommends the environment variable because command-line arguments appear in process
   listings and shell history.
