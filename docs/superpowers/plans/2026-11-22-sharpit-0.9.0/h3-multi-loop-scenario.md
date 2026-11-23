# Scenario: Tool calls on hosts with several event loops

## Coverage map

Active: D6 (tool calls must not introduce read-side effects), D8 (host integration), D10 (MCP/CLI parity). D1–D5, D7 and D9 do not cover loop selection, activation, masking, network scan failures, or pagination changes.

## Worst-case trace

Two `TestClient` instances serve the same app on distinct loops. `CaptureMiddleware.__call__` stores each request's loop in `ctx.capture.loop`; the later request overwrites the earlier loop. `running_host_loop(ctx)` in `engine/tools04/hostloop.py` returns that most recently stored loop. `_scan` in `engine/tools04/pentesting.py` then submits the current tool's coroutine to it with `run_coroutine_threadsafe`. The coroutine belongs to the host loop servicing the tool request, so it may run on the other TestClient loop; it can time out or return 503. `database_advisor_scan` has the same selection issue for async SQLAlchemy engines. A WSGI request has no captured loop, so `running_host_loop` returns `None` and these tools are unavailable.

## Scenario table

| # | Dimension | Scenario | Severity | Expected behaviour | Test |
|---|---|---|---|---|---|
| 1 | D8 | Two live request loops; each tool call arrives from a different loop | High | Each tool runs on the loop servicing its own MCP/CLI request | Integration |
| 2 | D8 | Selected request loop closes before work is submitted | High | Refuse with the existing unavailable response; do not fall back to a stale loop | Unit |
| 3 | D8 | WSGI host supplies no request loop | High | Provider makes loop unavailability explicit; tool refuses without creating a private loop or changing host state | Unit |
| 4 | D10 | CLI-only database actions use the provider | High | `via="cli"` still selects the CLI request loop | Integration |
| 5 | D10 | Pentest and database advisor action on single-loop host | Medium | Existing behavior and response remain unchanged | Integration |

## Must-cover before merge

- `test_each_tool_uses_the_loop_serving_its_request`
- `test_closed_request_loop_does_not_fall_back_to_another_loop`
- `test_wsgi_without_request_loop_returns_unavailable`
- `test_cli_database_actions_use_cli_request_loop`
- Existing single-loop tests remain unchanged.

## Deferred

None.

## Known-issues cross-reference

Issue #287; no related known-issues entry found.
