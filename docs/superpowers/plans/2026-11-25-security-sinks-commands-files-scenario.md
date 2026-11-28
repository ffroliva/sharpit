# Scenario: Security Sinks, Request Values in Commands and File Paths

Plan: `2026-11-25-security-sinks-commands-files.md`. Release unit: plans 1 and 2 in 0.10.0; the SQL and outbound URL
sinks are out of 0.10.0. Deviations D1-D8 are approved and taken as given; where a scenario needs a decision they do
not cover, it is listed under *Decisions required before Task 1*.

Code traced: `src/sharpit/engine/sensors/` and `src/sharpit/fastapi/` at `16990fa2`, Starlette 1.10.0, FastAPI 0.162.0,
CPython 3.13 on Windows, and BootUI `v2.5.0` source (`RequestValues.java`, `AgentRequestValues.java`,
`RequestPhaseInterceptor.java`).

## Coverage map

| Dimension | Active | Why |
|---|---|---|
| D1 Safe mode fails closed | yes | The holder keeps request values in memory: it must not exist while the console is inactive. |
| D2 Activation and access guard | yes | The `security-sinks` toggle is a POST action behind the existing gates; the guard chain itself is unchanged. |
| D3 Secret masking | yes | Request values must never reach a process row, a file row, a sink row, a log or an error. Main risk surface. |
| D4 BootUI contract parity | partly | Env name, limits and query decoding are parity items. The row and status shapes are plan 2's (D8). |
| D5 Introspection drift | yes | Ownership reads `scope["route"]`, `dependant`, `dependency_overrides` and route objects across versions. |
| D6 No side effects on reads | partly | No new GET route or read tool; the `java-agent` report lists one more toggle. The holder writes no file or socket. |
| D7 OSV/EPSS network failures | no | The change makes no network call. |
| D8 Host-app integration | yes | Middlewares that copy the scope, mounted apps, static files and catch-all routes change what the holder can read. |
| D9 Scale and limits | yes | Every BootUI limit is ported; the table, check and comparison budgets decide when a row falls back to `NOT_CHECKED`. |
| D10 MCP and CLI parity | partly | The enable and disable tools reach the same `switch_sensor_for_agents` (`floor.py:168-182`); their descriptions change in Task 6. |

## Worst-case trace

**Input.** A Windows host, request `GET /run?arg=aaaa&tool=evilx`, and an owned endpoint that runs
`subprocess.run(["evilx", "aaaa", "aaaa", "aaaa", "aaaa", "aaaa", "aaaa", "aaaa", "aaaa", "aaaa"])`. The same
shape reaches `os.system("evilx aaaa ...")` on any platform.

1. CPython's Windows `subprocess.Popen._execute_child` joins the list with `list2cmdline` and raises
   `subprocess.Popen` with `executable=None` and one string, `"evilx aaaa aaaa ..."` (D3, confirmed by the earlier
   probe).
2. `AuditHub._dispatch` (`audit.py:84-97`) hands it to `_deliver` (`audit.py:102-111`), which offers every row
   `ProcessesSensor.record` returns (`processes.py:94-96`).
3. `_target` (`processes.py:99-104`) maps the event through `_ARGV_AT` (`processes.py:83`) to
   `_argv_target(None, "evilx aaaa ...")` (`processes.py:71-79`): no program, no list, so `_program(line)`
   (`processes.py:41-68`) takes the first word: `"evilx"`. Today the process row's target is `"evilx"`.
4. With the plan's matcher (Task 4, Step 3), the one string is checked once. The held values are, in the order held,
   `arg="aaaa"` then `tool="evilx"` (Task 1, Step 3: path values, then query pairs in order). `Match.spans` carries
   `(index into the held values, start, end)`; BootUI emits spans **in value order**, at most `MAX_SPANS`, and sets
   `F_OVERFLOW` past it (`RequestValues.java:593-594`, `:997-1013`); the plan ports that order. Nine `aaaa` spans fill the eight slots; the
   `evilx` span at offset 0 is never reported. `redacted` is `None`.
5. The D3 rule for one string asks whether *a reported span* starts before the end of the program's first occurrence
   (`"evilx"`, end 5). None does, so the target is the program name, `"evilx"`. `unchecked(match)` is false, because
   `F_OVERFLOW` is not in `F_STOPPED | F_BUSY | F_PARTIAL` (Task 1, `unchecked`). The process row is published as
   `{"source": "processes", "target": "evilx"}`: the value of `tool`.

**Finding.** A request value reaches a process row (Critical, row 1). It does not happen for an argv list: element 0
is its own check there, as in BootUI (`RequestValues.java:697-711`), so only the joined-string branch that D3 adds is
exposed. The fail-closed reading of the global constraint ("no value in any row") is that an overflowed one-string
match counts as the executable holding a value. Must-cover: `test_an_overflowed_command_line_never_names_its_program`.

**Withdrawn on the way.**

- *A file path that overflows leaks through its pattern.* Task 4, Step 4 gives `redacted is None` the target
  `FROM_REQUEST_INPUT`, as `fileUsed` does (`RequestValues.java:741-764`). No gap.
- *The files sensor's path cache keeps a value after the request.* `_row` caches every raw path in `_seen`
  (`files.py:216-221`) and `_pair` keeps raw copy paths in `_pending` (`files.py:187-190`). Task 4, Step 4 checks
  before `_seen` is read or written, resolves a match without caching, and stores `hash(text)` in `_pending`; the
  plan's `test_no_cache_keeps_a_value_after_the_request` pins it. No gap for the install that holds the request.
  The case of a second install is row 14.
- *An exception text leaks a value through `hook_failed`.* `request_ended` runs inside `_request_end_guard`
  (`capture.py:131-135`), which records the exception text; `end` only pops a dict entry by request id, and its
  failure text holds no value. No gap.
- *The journal shows a secret-looking parameter name.* The journal masks every field by key and text at read
  (`journal.py:201-214`, `:384-407`); probed: a JWT-shaped `parameter` reads as `******`, the hashes and a
  `./reports/{name}.csv` target are unchanged. No gap.

**Second trace: the ownership cache.** Task 2, Step 3 caches the code set "in a `weakref.WeakKeyDictionary` keyed
by the route". Starlette's `Route` and `Mount` define `__eq__` without `__hash__`, so `APIRoute` is unhashable;
probed on Starlette 1.10.0: `WeakKeyDictionary()[APIRoute(...)] = ...` raises `TypeError: unhashable type`. `owned`
never raises, so every owned case would answer False and no sink row would ever be published (row 3). The cache
must key by identity (for example `id(route)` with a weak reference to confirm it), which keeps D1's "keyed by
`scope["route"]`". The plan's `test_only_the_endpoints_own_stack_is_owned` would fail on it; the must-cover row adds
the cache's own property, that the code set is built once per route.

## Scenario table

| # | Dimension | Scenario | Severity | Expected behaviour | Test |
|---|---|---|---|---|---|
| 1 | D3 | One joined command string whose matched spans overflow before the program's own span (Windows `Popen` list, `os.system`) | Critical | No process row or sink row names the program; the executable counts as holding a value | Unit |
| 2 | D1 | Console inactive (`SHARPIT_ENABLED=OFF` or a production profile) with the setting on and `processes`, `files`, `security-sinks` configured | Critical | No lane, no audit hook, nothing held; every request leaves `held() == 0` | Integration |
| 3 | D5 | Ownership cache keyed by an unhashable `APIRoute` | High | The code set is built once per route by identity; owned cases stay owned | Integration |
| 4 | D5 | A Starlette `HTTPEndpoint` called with `GET` and then `POST` on one route, after the first method's set was cached | High | Each method's handler is owned | Integration |
| 5 | D3, D4 | Command texts that are not `str`: a `pathlib.Path` argv element, `bytes` argv on POSIX, and `os.system`, whose event carries `bytes` on POSIX (`posixmodule.c` audits the FS-encoded command) | High | Each is checked in the decoded form `_text` gives (`processes.py:32-38`); element 0 is never `NOT_CHECKED` because of its type | Unit |
| 6 | D4 | Raw non-ASCII bytes in `query_string` (`q=caf\xc3\xa9`) | High | Decoded as Starlette reads them (latin-1, as `correlation.py:30` does), so the held value equals what the app received (`cafÃ©`) and nothing raises | Unit |
| 7 | D8 | A host ASGI middleware inside sharpit's that copies the scope before routing | High | The host response is unchanged; query values still redact; path values and ownership degrade to absent, no sink row, no error | Integration |
| 8 | D3 | Seeded canary value through a path open, a command and an exception, read back through every GET route and read tool | Critical | Absent everywhere but the request's own exchange and `http` rows | Integration (in plan, Task 5) |
| 9 | D3 | A check that races the end or clear of its request | Critical | Publishes nothing, inserts nothing | Unit (in plan, Task 1) |
| 10 | D1 | The sensor switched off, paused, detached or its capture hook suspended mid-request | Critical | Values wiped at once; later checks hold nothing | Integration (in plan, Task 5) |
| 11 | D9 | Not-owned work spends the request's check budget | High | Later endpoint checks are `NOT_CHECKED`, never named | Unit (in plan, Task 1 and D2) |
| 12 | D5 | Eager task factory: a child task's first step runs under the endpoint's frames | High | Owned, as documented | Integration (in plan, Task 2) |
| 13 | D3 | An explicit executable beside one string (Windows `shell=True`, `executable="X.exe"`) | High | The executable is checked on its own first | Unit (in plan, Task 4) |
| 14 | D8 | Two sharpit installs in one process; a request of install A opens a path holding its value | Medium | Install A redacts. Install B's matcher sees another context, records the path as today and caches the raw path in its own `_seen`. `SECURITY.md` states that only the request's own install redacts | Integration |
| 15 | D8 | Work handed to `loop.run_in_executor` or a raw thread, which copy no context | Medium | No request is visible: the row is recorded as today, unredacted. `SECURITY.md` names it | Integration |
| 16 | D5 | `app.dependency_overrides` changed after the first request cached the route's code set (common in test suites) | Medium | The override's code is owned; the cache follows the overrides or is keyed with them | Integration |
| 17 | D8 | A `StaticFiles` mount or an SPA catch-all `/{path:path}`: every request holds `path` | Medium | A StaticFiles mount holds no path value (Starlette's Mount consumes {path}): each served file's row reads ./static/<name> as today and no sink row is published. An SPA catch-all route /{path:path} holds path: an owned open inside the endpoint reads ./static/{path} and publishes a row | Integration |
| 18 | D9 | Common four-character values (`?format=json`, `?sort=name`) | Medium | Matched as BootUI matches: every path holding them is redacted and an owned open publishes a row; plan 2's confirmation separates them | Unit |
| 19 | D9 | A request that checks more than `MAX_CHECKS` distinct paths (template or asset loading) | Medium | Further rows are `NOT_CHECKED`, as BootUI | Unit (ported budget test covers the mechanism) |
| 20 | D4 | `query_string` replaced by a host middleware with a `str` or missing | Medium | Query values skipped; path values still read; no exception path to `F_BUSY` for every check | Unit |
| 21 | D4, D9 | A request with no query or path values reaches a sink | Medium | No entry is inserted (BootUI calls `begin` only when values exist, `RequestPhaseInterceptor.java:54-56`), so value-less requests never fill `ENTRIES` | Unit |
| 22 | D10 | `enable_agent_sensor` for `security-sinks` while the setting is off | Medium | Refused 409 with the existing not-armed text; the wording names an agent that sharpit does not have. Reword with plan 2's skill line | Integration |
| 23 | D3 | Windows: a value holding `/` joined by `pathlib`, which writes `\` | Medium | Not matched (verbatim matching, as BootUI on Windows); `SECURITY.md` says matching is verbatim | Unit |
| 24 | D9 | A live request older than `DEADLINE_SECONDS` (SSE, long upload) | Medium | Behaviour after the sweep to be decided (see below) and pinned by a test | Unit |
| 25 | D9 | More than `ENTRIES` concurrent requests holding values | Medium | The 129th gets an empty match, flags 0, as BootUI: its rows are recorded as today | Unit (ported table test) |
| 26 | D3 | Explicit `executable` with a different `argv[0]` display name on POSIX | Low | `argv[0]` is not checked; it reaches no row | Unit |
| 27 | D3 | A `NAME=value` prefix in `os.system` holding a value | Low | The span starts before the program ends, so the executable counts as holding a value: over-redaction, safe | Unit |
| 28 | D3 | A placeholder whose parameter name has digits or is a 24-letter mixed-case word | Low | Collapsed by `_collapse` (`files.py:93-97`) to `{file{n}}` or `{id}` in the file row; the sink row's `parameter` keeps the name | Unit |
| 29 | D4 | A float path parameter formatted differently by `str()` than in the URL (`10.50` against `10.5`) | Low | Matched as a substring, as BootUI's compare: the held text is str(value) (10.5) and it matches inside 10.50; over-redaction, the safe side | Unit |
| 30 | D1 | Only `security-sinks` switched on, `files` off, `processes` not configured | Low | `attach` enables a sensor with no events: the hook is installed and inert (`lane.py:61-66`, `audit.py:49-55`) | Integration |
| 31 | D3 | Case-folding file systems: a value differing in case from the path | Low | Not matched (verbatim) | Unit |

## Must-cover before merge (Critical + High)

New, added to their tasks in the plan:

| Row | Test | Task |
|---|---|---|
| 1 | `test_an_overflowed_command_line_never_names_its_program` | 4 |
| 2 | `test_an_inactive_console_holds_no_request_values_and_installs_no_hook` | 5 |
| 3 | `test_the_code_set_is_built_once_per_route_although_routes_are_unhashable` | 2 |
| 4 | `test_a_class_endpoint_owns_each_method_after_another_was_cached` | 2 |
| 5 | `test_pathlike_and_bytes_command_texts_are_checked_decoded` | 4 |
| 6 | `test_raw_query_bytes_are_read_as_starlette_reads_them` | 1 |
| 7 | `test_a_middleware_that_copies_the_scope_degrades_without_error` | 5 |

Already in the plan: rows 8 to 13 (`test_a_seeded_value_reaches_no_route_log_or_error`,
`test_a_check_after_end_or_clear_publishes_and_inserts_nothing`, `test_switching_the_sensor_off_wipes_held_values_at_once`,
`test_a_repeated_miss_costs_no_comparison_budget` with `test_work_not_owned_never_hides_the_endpoints_later_row`,
`test_eager_task_first_step_is_owned_as_documented`, `test_an_explicit_executable_beside_one_string_is_checked_on_its_own`).

## Deferred (Medium + Low)

File as issues after the plan merges, except rows 14, 15 and 23, whose limitation lines belong in the `SECURITY.md`
paragraph of Task 6, and row 24, which waits on the decision below. Suggested test names: row 16
`test_a_dependency_override_set_after_the_first_request_is_owned`; row 17
`test_a_static_files_mount_redacts_its_rows_and_publishes_no_sink`; row 20
`test_a_query_string_that_is_not_bytes_is_skipped`; row 21 `test_a_request_without_values_inserts_no_entry`.

## Decisions required before Task 1

Decided: all three follow BootUI. D6 keeps a value under no name and decodes invalid UTF-8 with replacement; a request past the deadline holds no values again; D3 states the overflow rule. The plan's D3, D6 and Task 1 carry them.

These differ from BootUI in ways D1-D8 do not record. Each needs the same approval as the table's rows, then a line in
`docs/reference/matrix-updates/0.10.0-security-sinks.tsv`.

1. **D6 skips values BootUI keeps.** BootUI's `addQuery` skips a pair only when its *value* fails to decode; a pair
   whose name fails keeps its value under a `null` name (`AgentRequestValues.java:227-233`, `:276-281`), shown by
   position. Java's `URLDecoder` also replaces invalid UTF-8 after percent-decoding with U+FFFD instead of failing,
   while `unquote_plus(errors="strict")` raises on `%E9` (probed), and Starlette hands the app `"�"`. As written,
   `?%ZZ=../../etc/passwd` and `?f=report%E9q3` hold nothing in sharpit: the path is neither redacted nor reported.
   Either follow BootUI (keep the value; a nameless value is named by position; decode with replacement) or log both
   as deviations.
2. **A live request past `DEADLINE_SECONDS`.** BootUI pushes values once at the handler phase; after the sweep pops
   them, the request's later checks find nothing. With D4's lazy read, sharpit's next check would read the scope
   again and insert a fresh entry with a fresh budget. Pin one behaviour; the second is a deviation row.
3. **D3's joined-string rule and overflow.** Row 1's fix (an overflowed one-string match counts as the executable
   holding a value) follows from the global constraint, and D3's text should say so.

## Known-issues cross-reference

- `KNOWN_ISSUES.md` does not exist.
- Open GitHub issues: none touches the audit sensors, ownership or request values (#334, security-advisor messages
  lost on sensitive-looking file names, is unrelated).
- Spec deviation log §14: no entry for the sensors; the matrix fragment of Task 6 carries D1-D8 and any decision
  above.

## Not checked

- Linux and macOS argument types were read from CPython's source, not probed on those platforms (row 5).
- Free-threaded CPython 3.14t: the holder's lock-free `end` and `clear` against inserts.
- The floor versions (FastAPI 0.115, Starlette 0.40) for rows 3 and 4; `Route.__eq__` predates them.
- A live `BaseHTTPMiddleware` run and a live `uvicorn` server; the ownership evidence is the earlier probes.
