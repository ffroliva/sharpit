# User-facing text for the owner (O3)

- Panel `traces`: OpenTelemetry spans the application already produces, grouped by trace (list, waterfall detail,
  clear). sharpit never installs or replaces a `TracerProvider`: it adds one span processor to the application's own
  SDK provider at startup. Without `opentelemetry-sdk`, or with the API's no-op provider, the panel says why.
- A provider set after the app started is picked up at the next restart (the SDK cannot remove a processor).
- Span attributes are masked at read (SQL text, credential headers, URL userinfo/query secrets); timestamps are epoch
  nanoseconds, as in BootUI.
- SKILL row: `traces` — "OTel spans from the app's own SDK provider; `get_traces` (MCP), `clear_traces` (action)".
- API: `GET /sharpit/api/traces?limit=100` (clamped 1..500), `GET /sharpit/api/traces/{traceId}`,
  `DELETE /sharpit/api/traces` (204; 403 when read-only).
