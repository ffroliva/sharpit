# Settings

Every setting is an environment variable and an `install()` keyword. **The environment variable wins over the
keyword**, so a deployment can always force `SHARPIT_ENABLED=OFF`. An empty value counts as unset. The name rule is
`SHARPIT_` + the keyword in upper case. An invalid value never raises: that setting takes its fail-safe value
(disabled, read-only, masked) and a warning is recorded and shown on the Overview panel. Only an unusable `path` or
`api_path` raises `ValueError`, and an unknown keyword raises `TypeError` with a suggestion. Booleans accept
`true/false/yes/no/on/off/1/0`; durations accept `10s`, `500ms` or a bare number of seconds.

| Env var | Keyword | Default | Meaning |
|---|---|---|---|
| `SHARPIT_ENABLED` | `enabled` | `AUTO` | `ON`, `OFF` or `AUTO` (see [Activation](activation.md)) |
| `SHARPIT_ENABLED_PROFILES` | `enabled_profiles` | `dev,local,development` | profiles that turn it on |
| `SHARPIT_DISABLED_PROFILES` | `disabled_profiles` | `prod,production` | profiles that turn it off |
| `SHARPIT_PROFILE_VARS` | `profile_vars` | `SHARPIT_PROFILES,APP_ENV,ENVIRONMENT` | variables the profiles are read from |
| `SHARPIT_PATH` | `path` | `/sharpit` | console mount point |
| `SHARPIT_API_PATH` | `api_path` | `/sharpit/api` | must sit under `path` |
| `SHARPIT_ALLOW_NON_LOCALHOST` | `allow_non_localhost` | `false` | accept non-loopback callers (token required) |
| `SHARPIT_ALLOWED_HOSTS` | `allowed_hosts` | empty | extra `Host` names to accept |
| `SHARPIT_TRUSTED_PROXIES` | `trusted_proxies` | empty | proxy addresses or ranges admitted as remote callers (token still required) |
| `SHARPIT_TRUST_CONTAINER_GATEWAY` | `trust_container_gateway` | `OFF` | `AUTO` trusts the detected container gateway |
| `SHARPIT_AUTHENTICATION_TOKEN` | `authentication_token` | generated | bearer token for untrusted sources |
| `SHARPIT_READ_ONLY` | `read_only` | `false` | refuse every write action |
| `SHARPIT_PANELS_<ID>_ENABLED` | `panels={"<id>": {"enabled": ...}}` | `true` | per-panel switch |
| `SHARPIT_PANELS_<ID>_READ_ONLY` | `panels={"<id>": {"read_only": ...}}` | `false` | per-panel read-only; `<ID>` is the panel id in capitals with `-` as `_`: `OVERVIEW`, `CONFIG`, `MAPPINGS`, `LOGGERS`, `BEANS`, `VULNERABILITIES`, `HTTP_EXCHANGES`, `EXCEPTIONS`, `SQL_TRACE`, `ACTIVITY`, `LOG_TAIL`, `ALEMBIC`, `DATABASE_CONNECTION_POOLS`, `HEALTH`, `THREADS`, `REST_API`, `HTTP_PROBE`, `MCP_SERVER`, `CLI` |
| `SHARPIT_EXPOSE_VALUES` | `expose_values` | `MASKED` | `MASKED`, `METADATA_ONLY` or `FULL` (FULL logs a warning) |
| `SHARPIT_MASK_SECRETS` | `mask_secrets` | `true` | mask secret-looking names and values; sharpit's own token is masked even when `false` |
| `SHARPIT_SHOW_BANNER` | `show_banner` | `true` | print the startup banner to stderr |
| `SHARPIT_STATE_DIR` | `state_dir` | `.sharpit` | where dismissed vulnerability rules are stored (`sharpit.yml`, created on first write) |
| `SHARPIT_CONFIG_SCAN` | `config_scan` | `true` | `true` scans your top-level package for `os.getenv` keys, `false` disables, or a list of package names |
| `SHARPIT_VULNERABILITIES_OSV_ENABLED` | `vulnerabilities_osv_enabled` | `true` | allow the OSV scan |
| `SHARPIT_VULNERABILITIES_OSV_BASE_URI` | `vulnerabilities_osv_base_uri` | `https://api.osv.dev` | OSV endpoint |
| `SHARPIT_VULNERABILITIES_EPSS_ENABLED` | `vulnerabilities_epss_enabled` | `true` | enrich findings with EPSS scores |
| `SHARPIT_VULNERABILITIES_EPSS_BASE_URI` | `vulnerabilities_epss_base_uri` | `https://api.first.org` | EPSS endpoint |
| `SHARPIT_VULNERABILITIES_REQUEST_TIMEOUT` | `vulnerabilities_request_timeout` | `10s` | per-request timeout |
| `SHARPIT_VULNERABILITIES_MAX_PACKAGES` | `vulnerabilities_max_packages` | `500` | packages sent to OSV |
| `SHARPIT_VULNERABILITIES_MAX_ADVISORIES` | `vulnerabilities_max_advisories` | `200` | advisories kept per scan |
| `SHARPIT_MCP_ENABLED` | `mcp_enabled` | `OFF` | `ON` enables the MCP endpoint |
| `SHARPIT_MCP_MAX_RESULTS` | `mcp_max_results` | `200` | cap on items per tool call |
| `SHARPIT_MCP_MAX_PAYLOAD_BYTES` | `mcp_max_payload_bytes` | `1048576` | largest request body |
| `SHARPIT_MCP_MAX_CONCURRENT_CALLS` | `mcp_max_concurrent_calls` | `20` | parallel tool calls |
| `SHARPIT_MCP_EXECUTION_TIMEOUT` | `mcp_execution_timeout` | `30s` | per tool call |
| `SHARPIT_MCP_MAX_RESPONSE_BYTES` | `mcp_max_response_bytes` | `4194304` | largest response body |
| `SHARPIT_CLI_ENABLED` | `cli_enabled` | `true` | enable the `/sharpit/api/cli` endpoint |
| `SHARPIT_CLI_MAX_RESULTS` | `cli_max_results` | `200` | cap on items per call |
| `SHARPIT_CLI_MAX_CONCURRENT_CALLS` | `cli_max_concurrent_calls` | `20` | parallel calls |
| `SHARPIT_CLI_EXECUTION_TIMEOUT` | `cli_execution_timeout` | `30s` | per call |
| `SHARPIT_HTTP_EXCHANGES_MAX_EXCHANGES` | `http_exchanges_max_exchanges` | `200` | HTTP exchanges ring buffer size |
| `SHARPIT_EXCEPTIONS_MAX_GROUPS` | `exceptions_max_groups` | `100` | max exception groups retained |
| `SHARPIT_EXCEPTIONS_MAX_OCCURRENCES_PER_GROUP` | `exceptions_max_occurrences_per_group` | `25` | occurrences kept per exception group |
| `SHARPIT_EXCEPTIONS_MAX_STACK_FRAMES` | `exceptions_max_stack_frames` | `50` | stack frames kept per exception |
| `SHARPIT_SQL_TRACE_ENABLED` | `sql_trace_enabled` | `true` | attach SQLAlchemy event listeners |
| `SHARPIT_SQL_TRACE_RECORDING` | `sql_trace_recording` | `true` | initial SQL trace recording state |
| `SHARPIT_SQL_TRACE_CAPTURE_PARAMETERS` | `sql_trace_capture_parameters` | `false` | capture SQL bind parameters |
| `SHARPIT_SQL_TRACE_CAPTURE_CALL_SITE` | `sql_trace_capture_call_site` | `true` | capture call-site stack frame |
| `SHARPIT_SQL_TRACE_MAX_ENTRIES` | `sql_trace_max_entries` | `200` | SQL trace ring buffer size |
| `SHARPIT_SQL_TRACE_SLOW_QUERY_THRESHOLD_MILLIS` | `sql_trace_slow_query_threshold_millis` | `100` | slow query threshold in milliseconds (0 disables) |
| `SHARPIT_SQL_TRACE_MAX_SQL_LENGTH` | `sql_trace_max_sql_length` | `2000` | max character length of captured SQL |
| `SHARPIT_SQL_TRACE_MAX_PARAMETER_LENGTH` | `sql_trace_max_parameter_length` | `200` | max character length of captured parameter values |
| `SHARPIT_SQL_TRACE_N_PLUS_ONE_THRESHOLD` | `sql_trace_n_plus_one_threshold` | `5` | duplicate query threshold for N+1 detection (min 2) |
| `SHARPIT_ACTIVITY_MAX_ENTRIES` | `activity_max_entries` | `200` | max entries returned by activity queries |
| `SHARPIT_ACTIVITY_REQUEST_SLOW_THRESHOLD_MS` | `activity_request_slow_threshold_ms` | `1000` | slow request threshold in milliseconds |
| `SHARPIT_ACTIVITY_N_PLUS_ONE_THRESHOLD` | `activity_n_plus_one_threshold` | `5` | per-request query threshold for N+1 detection (min 2) |
| `SHARPIT_LOG_TAIL_MAX_LINES` | `log_tail_max_lines` | `500` | max lines kept in log tail buffer |
| `SHARPIT_LOG_TAIL_MAX_BYTES` | `log_tail_max_bytes` | `1048576` | max memory in bytes for log tail buffer (must be > 0) |
| `SHARPIT_ALEMBIC_CONFIG` | `alembic_config` | `alembic.ini` | path to Alembic configuration file |
| `SHARPIT_ALEMBIC_TIMEOUT` | `alembic_timeout` | `5s` | timeout for Alembic database reads |
| `SHARPIT_HEALTH_TIMEOUT` | `health_timeout` | `5s` | timeout per health check |
| `SHARPIT_THREADS_MAX_STACK_FRAMES` | `threads_max_stack_frames` | `64` | max stack frames per thread or task |
| `SHARPIT_ADVISORS_MAX_RETAINED_VIOLATIONS` | `advisors_max_retained_violations` | `10000` | max retained violations per advisor scan |
| `SHARPIT_STREAM_MAX_SECONDS` | `stream_max_seconds` | `3s` | duration before closing and rotating SSE streams |

The first Config load scans your package's source for `os.getenv` keys and caches the result. On a large application
that one-time scan can take several seconds. Set `SHARPIT_CONFIG_SCAN=false` to skip it, or narrow it to the smaller
top-level packages that read settings (`SHARPIT_CONFIG_SCAN=billing_config,accounts`; a dotted name scans its whole
top-level package).
