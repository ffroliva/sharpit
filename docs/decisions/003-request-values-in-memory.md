# Request values in memory

## Status

Implemented for command and file path sinks. Request-value matching is opt-in and disabled by default.

## Decision

When `SHARPIT_AGENT_SECURITY_SINKS_REQUEST_VALUES=true` and the security-sinks sensor is enabled, sharpit reads eligible query and path parameter values from the request scope at the first sink check. It holds them in a bounded in-memory entry for the lifetime of the request, up to 60 seconds, and drops the entry when the request ends. The matcher compares values verbatim against command arguments and file paths. It does not follow transformations or track taint. Matching values are redacted from process and file rows; an owned match may produce a `request-input-in-sink` row in Side Effects.

The Side Effects store retains only masked row fields and in-memory hashes used for confirmation. Hashes are never emitted. Secret-looking parameter names and path segments are masked at every output exposure. A request that has no route template is attributed using the path already reduced by capture, then masked per segment.

This release checks command and file path sinks only. SQL statements and outbound URLs are not checked. Work performed after the endpoint returns, including a `FileResponse` opening a file in a worker thread, is not owned by the request. Absence of a finding is not evidence that the application is safe.

## Rationale

Request-scoped, bounded retention allows sharpit to identify an unchanged request value at a supported sink without keeping the value in a row, log, exception, or output. Opt-in activation makes the additional comparisons explicit. Matching unchanged text gives a narrow observation with a clear limit: transformed values and work outside the endpoint's live request are not covered.

## Consequences

The feature requires both the `security-sinks` sensor and `SHARPIT_AGENT_SECURITY_SINKS_REQUEST_VALUES=true`. It covers commands and file paths only; SQL and outbound URLs remain outside this release. A missing row must not be interpreted as a safety verdict.

## Enforced by

- `src/sharpit/engine/sensors/sinks/values.py` implements bounded request-value matching; the sensor and store tests cover retention, redaction, and confirmation.
- `src/sharpit/engine/collectors/sideeffects/display.py` masks and presents Side Effects rows; `tests/engine/collectors/sideeffects/test_display.py` and `tests/safety/test_security_sinks_rows_safety.py` cover the output boundaries.
