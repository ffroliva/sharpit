# Scenario: Security Sinks, Visible Rows

Plan: `2026-11-26-security-sinks-visible-rows.md`. Release unit: plans 1 and 2 in 0.10.0; SQL and outbound URL sinks
are out of 0.10.0. Decisions (a) to (e), deviation N1, the conditional N2 and adaptations F1 to F6 are taken as given;
a scenario that needs a decision they do not cover is listed in the plan under *Open deviations*.

Code traced: `src/sharpit/engine/sensors/`, `src/sharpit/engine/capture/`, `src/sharpit/engine/masking.py` and
`src/sharpit/fastapi/routes/side_effects.py` at `349af364` (plan 1 Tasks 1 to 3 merged), CPython 3.13 on Windows, and
BootUI `v2.5.0` source (`SideEffectsStore.java`, `SideEffectsService.java`, `SinkWording.java`,
`SideEffectOrigins.java`, `JournalRequestRoutes.java`, the side-effects DTOs).

## Coverage map

| Dimension | Active | Why |
|---|---|---|
| D1 Safe mode fails closed | yes | The rings and the store hold rows derived from request input; they must not exist while the console is inactive. |
| D2 Activation and access guard | yes | Two existing GET routes and one tool start returning rows; the guard chain is unchanged and must still stand in front of them. |
| D3 Secret masking | yes | Main risk surface: parameter names, file targets, route labels, hashes, and the `FULL` and `METADATA_ONLY` exposures. |
| D4 BootUI contract parity | yes | Four DTOs, confirmation, owner resolution, wording and limitation texts are ports. |
| D5 Introspection drift | partly | Only the call-site label (`co_qualname`, greenlet parent) and plan 1's ownership walk; route labels come from the journal, not from route objects. |
| D6 No side effects on reads | yes | Reads now drain rings and resolve owners: in-memory only, never a socket, file, logger or environment change. |
| D7 OSV/EPSS network failures | no | The change makes no network call. |
| D8 Host-app integration | partly | Route labels for mounted apps and untemplated paths; the host's lifespan as the readiness instant (Open deviation O3). |
| D9 Scale and limits | yes | Ring capacity, store caps, 10 000 waiting observations, a file flood between reads, concurrent drains. |
| D10 MCP and CLI parity | yes | `get_side_effects` and `sharpit side-effects` share one implementation; advertising follows the lane. |

## Worst-case trace

**Input.** `GET /read/quarterly?AKIAIOSFODNN7EXAMPLE=quarterly`, an owned endpoint that opens
`reports/quarterly.csv`, under `SHARPIT_EXPOSE_VALUES=FULL`, then a read of `GET {api}/side-effects/sensor?sensor=security-sinks`.

1. `values.py:58` accepts the name: `_NAME` allows 1 to 64 characters of `[A-Za-z0-9_.\-\[\]]`, as BootUI does
   (`RequestValues.java:565`). `valid_name("AKIAIOSFODNN7EXAMPLE")` is True (probed).
2. `values.py:208-219` redacts the path to `reports/{AKIAIOSFODNN7EXAMPLE}.csv`: the placeholder is the parameter's
   name.
3. `matcher.py:73-81` publishes the sink row with `"parameter": name`, verbatim.
4. The files sensor finishes the target with `_collapse(self._mask(pattern))` (`files.py:246-247`). `self._mask` is the
   install's `masker.mask_path` (`fastapi/capture.py:282-283`), which returns the path unchanged under `FULL`
   (`masking.py:647`). `_collapse` then turns the alphanumeric run, which has digits and is at least 12 long, into
   `{id}` (`files.py:78-90`): the target reads `./reports/{{id}}.csv` (probed). A `ghp_` token name collapses to
   `{ghp_{id}}` (probed).
5. In BootUI the row would show `parameter = "AKIAIOSFODNN7EXAMPLE"` (`SideEffectsService.java:2648-2658`) and a
   `detail` holding it in backquotes (`SinkWording.java:31`).

**Finding.** Without N1 the name reaches `parameter` and `detail` verbatim under every exposure (Critical, row 1):
N1's test is the must-cover. The target is not exposed in the traced cases: under `MASKED` the segment is masked before
the collapse (`is_secret_value("{AKIAIOSFODNN7EXAMPLE}.csv")` is True, probed), and under `FULL` the collapse reshapes
it. A secret-looking name that the collapse leaves intact is not excluded by this trace, so row 1 also pins the target;
if that test is red after the plan's per-segment mask, the fix is Open deviation O5.

**Withdrawn on the way.**

- *The hashes leak through the journal under `FULL`.* No reader takes sink rows from the journal (decision (a)); the
  journal's `records` still masks them by key at read (`journal.py:379-407`), and no route returns the
  `security-sinks` source's records. No gap.
- *A route reader over masked records names nothing under `METADATA_ONLY`.* `masker.mask` answers `None` for every
  value there (`masking.py:566-567`), so `records("http")` would carry no `requestId` or `route`. The plan's
  `request_routes` reads raw events as BootUI's reader does (`JournalRequestRoutes.java:50-66`) and masks the
  attribution at output. No gap; row 11 pins it.
- *A file flood blinds the security-sinks rows.* With one shared ring, frequent file rows would fill it and drop the
  rare sink rows. The plan gives each sensor its own ring and drop count, as BootUI counts drops per sensor
  (`agent/bridge/SideEffects.java:53`). Row 9 pins it.

**Second trace: the recording clear.** BootUI's `RECORDING_CLEARED` says a record "the agent still held whose first
occurrence came before the clear" is dropped too (`SideEffectsService.java:233-234`). With a drain on read, a row
appended before the clear but never drained would otherwise reach the store at the next read. The plan's
`SensorHook.discard` clears that sensor's ring and bumps its generation, and the store clears the sensor when the
generation changed (Tasks 5 and 7). Row 10 pins both halves.

## Scenario table

| # | Dimension | Scenario | Severity | Expected behaviour | Test |
|---|---|---|---|---|---|
| 1 | D3 | A secret-looking parameter name (`AKIAIOSFODNN7EXAMPLE`, a `ghp_` token, a JWT) at `MASKED`, `METADATA_ONLY` and `FULL` | Critical | `parameter` and `detail` show `******` (N1); no `target` holds the name or a recognisable part of it | Unit |
| 2 | D3 | A canary query value through a path open, a command and a confirming second request, read back through every side-effects route, page, tool query and CLI command at every exposure | Critical | Neither the canary nor `rawHash`, `redactedHash` or any hash's decimal form appears | Integration |
| 3 | D3 | `get_side_effects` queried with the seeded value, its case variant or a substring, as an oracle | Critical | `matched == 0` every time: matching never reads a value, a hash or `detail` | Integration |
| 4 | D1 | Console inactive with the setting and the three sensors configured | Critical | No ring, no store; every side-effects path answers 404 | Integration |
| 5 | D6 | A read that drains queued rows and resolves owners | Critical | `no_side_effects` holds for each route and tool | Integration |
| 6 | D3 | A file target with a secret-shaped segment at each exposure | Critical | Masked per segment at every exposure; under `METADATA_ONLY` no BootUI-filled key is `None` | Unit |
| 7 | D3 | sharpit's token as a path segment of a file a request opens | Critical | Never shown, at any exposure | Unit |
| 8 | D2 | A cross-site, foreign-origin or forwarded read of the two routes while rows are queued | Critical | The guard refuses; the body holds no row | Integration |
| 9 | D9 | A file flood fills the `files` ring between two reads, then one sink row | High | The sink row is shown; `files` counts its drops; `security-sinks` drops nothing | Unit |
| 10 | D4 | A row appended before a recording clear and drained after it | High | Not shown; `RECORDING_CLEARED` is listed | Unit |
| 11 | D4 | `METADATA_ONLY` exposure | High | Routes are still named and two requests still confirm a row | Unit |
| 12 | D4 | The request's `http` event evicted before the read | High | The row waits, then counts under `(unknown route)` after 30 s | Unit |
| 13 | D4 | A read while the request still runs (its `http` event is written at the end) | High | The row waits; it is not shown under `(unknown route)` before 30 s, and is attributed once the event arrives | Unit |
| 14 | D9 | Four hook threads appending while a reader drains | High | Each row reaches the store exactly once; the hook thread takes no lock | Unit |
| 15 | D10 | `get_side_effects` with no lane, with the lane detached, and with a ringed sensor on | High | Listed on MCP only in the last case; otherwise the unavailable-tool answer with the panel's reason; the CLI manifest lists it always | Integration |
| 16 | D10 | The same query over MCP and the CLI | High | Same rows, caps and masking | Integration |
| 17 | D4 | A `file-path` journal kind reaching the wording | High | DTO `kind` reads `file path` and the file sentence is chosen, not the generic one | Unit |
| 18 | D9 | 2 000 rows and 10 000 waiting observations at one read | Medium | One read sorts and resolves within the existing route test timeouts; the journal lock is held only to copy | Unit |
| 19 | D8 | A request whose route has no template (a mounted `StaticFiles`, a 404 path that still opens a file) | Medium | The attribution is the request path masked per segment, as BootUI's route label and `maskPath` give; `SECURITY.md` says so | Integration |
| 20 | D1 | The files sensor switched off after rows were drained | Medium | Its drained rows stay until a recording clear, as BootUI keeps a run's rows; the sensor DTO reads `disabled` | Integration |
| 21 | D9 | Racing increments of the holder counters | Low | Counts may lose an increment; the `shortcut:` comment says so; the line stays advisory | Unit |
| 22 | D10 | A prompt-injected `query` (control characters, 10 000 characters) and a `limit` of 10 000 | Medium | Schema-validated; `limit` clamped to 500; the "No row matched" line echoes only the agent's own query | Integration |
| 23 | D5 | A call site inside a lambda, a nested function and a class body | Low | `co_qualname` gives `outer.<locals>.inner`, `<lambda>`, `Cls`; rows group by it | Unit |
| 24 | D4 | The holder line with the setting on and nothing checked yet | Medium | `"Request-value matching: 0 requests held values, 0 sink checks ran."` is listed, as BootUI lists it | Unit |
| 25 | D3 | A file target holding HTML (`<img src=x onerror=alert(1)>`) rendered by the view | High | Shown as text; no element added | Component (vitest) |
| 26 | D8 | A host app without a lifespan | Low | No row counts under `startup` (Open deviation O3) | Integration |
| 27 | D9 | The store at its caps while the ring keeps filling | Low | Past the caps rows fold into the Other row; unconfirmed ones count in `unconfirmedPastCap` only | Unit (ported cap test) |

## Must-cover before merge (Critical + High)

New, added to their tasks in the plan:

| Row | Test | Task |
|---|---|---|
| 1 | `test_a_secret_looking_parameter_name_is_masked_in_parameter_and_detail_at_every_exposure`, `test_a_secret_looking_parameter_name_never_reaches_a_target_at_any_exposure` | 9 |
| 2 | `test_a_seeded_value_and_the_hashes_reach_no_side_effects_output_at_any_exposure` | 12 |
| 3 | `test_a_query_holding_the_seeded_value_matches_no_row` | 11 |
| 4 | `test_an_inactive_console_builds_no_ring_or_store_and_answers_404` | 10 |
| 5 | `test_side_effects_reads_have_no_side_effects` | 12 |
| 6 | `test_every_exposure_masks_secret_segments_and_never_blanks_a_row` | 9 |
| 7 | `test_the_console_token_in_a_path_is_never_shown` | 9 |
| 8 | `test_a_cross_site_or_forwarded_read_of_side_effects_rows_is_refused` | 12 |
| 9 | `test_a_file_flood_never_drops_a_security_sinks_row` | 5 |
| 10 | `test_a_row_queued_before_a_clear_is_never_shown_after_it` (ring and store halves) | 5, 7 |
| 11 | `test_metadata_only_keeps_confirmation_and_routes` | 8 |
| 12 | `test_a_request_whose_http_event_was_evicted_counts_under_unknown_route` | 8 |
| 13 | `test_a_running_requests_rows_wait_for_its_route` | 8 |
| 14 | `test_a_read_racing_appends_loses_and_duplicates_nothing` | 5 |
| 15 | `test_get_side_effects_is_listed_only_while_a_side_effects_sensor_records` | 11 |
| 16 | `test_mcp_and_cli_side_effects_answer_the_same_rows` | 11 |
| 17 | `test_a_file_row_reads_file_path_and_its_sentence` | 10 |
| 25 | `renders row text as text, never as HTML` (vitest) | 13 |

## Deferred (Medium + Low)

File as issues after the plan merges, except row 19, whose sentence belongs in Task 14's `SECURITY.md` paragraph, and
rows 24 and 26, which Tasks 10 and 8 cover with the holder-line and readiness tests. Suggested test names: row 18
`test_one_read_at_the_caps_sorts_and_resolves_in_bounded_time`; row 20
`test_a_switched_off_sensor_keeps_its_drained_rows_until_a_clear`; row 22
`test_an_oversized_query_and_limit_are_bounded`; row 23 `test_call_site_labels_for_lambdas_and_nested_functions`.

## Known-issues cross-reference

- `KNOWN_ISSUES.md` does not exist.
- The spec's deviation log carries no side-effects entry; the matrix fragment `0.10.0-security-sinks.tsv` (plan 1,
  Task 6) receives N1, N2, F1 to F6 and every approved open deviation (plan 2, Task 14). `w6-S2.tsv:8,16,17,18,37`
  describe today's unavailable floor and are updated in Task 11.

## Not checked

- Free-threaded CPython 3.14t: the lock-free ring append and the counters.
- A live `uvicorn` run with a real browser for row 25; the evidence is the vitest component test.
- Whether any secret-looking name survives `files.py`'s collapse unchanged (row 1's target half): the plan's test
  decides, and O5 holds the fix.
