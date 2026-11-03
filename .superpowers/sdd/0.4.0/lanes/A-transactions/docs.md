# Transactions panel

The Transactions panel keeps a bounded in-memory record of SQLAlchemy connection transaction events. It does not issue SQL. Nested savepoints appear as child entries. SQL Trace statement counts are correlated from the SQL Trace ring when the report is read.

## Settings

| Setting | Environment variable | Default | Purpose |
|---|---|---:|---|
| `transactions_enabled` | `SHARPIT_TRANSACTIONS_ENABLED` | `true` | Enables transaction capture for the panel. |
| `transactions_recording` | `SHARPIT_TRANSACTIONS_RECORDING` | `true` | Starts or pauses capture at install. |
| `transactions_max_entries` | `SHARPIT_TRANSACTIONS_MAX_ENTRIES` | `200` | Maximum retained entries. |
| `transactions_slow_transaction_threshold_millis` | `SHARPIT_TRANSACTIONS_SLOW_TRANSACTION_THRESHOLD_MILLIS` | `200` | Duration at which an entry is marked slow. |
| `transactions_connection_hold_threshold_millis` | `SHARPIT_TRANSACTIONS_CONNECTION_HOLD_THRESHOLD_MILLIS` | `500` | Duration at which a connection is marked held. |

The recorder attaches when SQLAlchemy is available and retries on app startup or the first request if the library is imported later. `readOnly` and `isolation` are null because SQLAlchemy does not expose the needed intent through these connection events; the listener never queries for it.

## API and tools

- `GET /sharpit/api/transactions` returns the cached report.
- `GET /sharpit/api/transactions/stream` emits an `update` event when the report changes.
- `POST /sharpit/api/transactions/clear` clears retained entries.
- `POST /sharpit/api/transactions/recording` accepts `{"enabled": true|false|null}`; a missing or null value toggles recording.
- MCP exposes the read-only `get_transactions` tool. CLI actions are `clear_transactions`, `pause_transaction_recording`, and `resume_transaction_recording`.

The API writes and CLI actions follow sharpit's panel read-only policy. Transaction rows and error messages are masked before they leave the recorder.
