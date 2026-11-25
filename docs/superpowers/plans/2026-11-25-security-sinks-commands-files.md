# Security Sinks: Request Values in Commands and File Paths Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record, as opt-in runtime journal rows, that a query or path value of the current request reached a started command or a file path unchanged, without keeping the value.

**Architecture:** A bounded, per-context holder reads a request's values from its ASGI scope at the first sink check and drops them when the request ends. The existing `processes` and `files` audit sensors ask it whether an argument or a path holds a value, redact their own row when it does, and add a `security-sinks` row when the request's own endpoint or dependency is on the current stack.

**Tech Stack:** Python 3.12+ standard library, the resident audit hook (`engine/sensors/audit.py`), pytest. No new dependency.

**Spec:** BootUI at tag `v2.5.0`, read as source: `bootui-agent-bridge/src/main/java/io/github/jdubois/bootui/agent/bridge/RequestValues.java` (holder, `compare`, `redactChecked`, `commandStarted`, `fileUsed`, `callerRequest`), tests `RequestValuesTests.java` and `RequestValuesSinksTests.java` in the same module, and `bootui-engine/.../javaagent/AgentSensorSettings.java` (`SECURITY_SINKS`). Use `git -C <bootui clone> show v2.5.0:<path>`.

## Scope

This plan is the first of four. Each later plan produces its own working change:

1. **This plan:** holder, matching, command and file sinks, journal rows, toggle.
2. Rows, confirmation by a second request (`SideEffectsStore.confirmed`), wording (`SinkWording`), the Side Effects panel and the `request-input-in-sink` insight.
3. SQL sink (`RequestInputSinks.sql`, `SqlSinkText`). A SQLAlchemy async statement runs in a greenlet, whose frame chain ends at the greenlet; ownership there needs its own design.
4. Outbound URL sink (`RequestInputSinks.url`).

Out of scope: `SecuritySinks.java` (deserialization, weak algorithms, trust managers), the assessment header, and any shell or leading-dash rule, which BootUI does not have.

## Gates before Task 1

- [ ] Run `/sharpit:predict` and `/sharpit:scenario` on this plan; add each accepted scenario as a test to its owning task.
- [ ] Run `/sharpit:llm-council --tier high` on this plan: it holds request values in memory and changes what two sensors record. A finding that contradicts a deviation below stops the plan.
- [ ] Obtain the owner's approval of the five deviations below; each then becomes one line of `docs/reference/matrix-updates/0.10.0-security-sinks.tsv` (Task 6).

### Deviations from BootUI

| # | BootUI | sharpit | Reason |
|---|---|---|---|
| D1 | Owner slots and scopes decide whether work belongs to the request | The endpoint's or one of its dependencies' code objects is on the current Python stack | A context copy reaches sync endpoints, `to_thread` and child tasks alike; task and thread identity cannot tell them apart. A 15-case probe, with and without `BaseHTTPMiddleware`, separated all of them by frame |
| D2 | Ownership is checked before matching | Matching first, then ownership; work that is not the endpoint's own publishes no sink row, but its process or file row is still redacted | The walk costs about 34 µs at 60 frames, so only a match pays it; the redaction is stricter than BootUI's |
| D3 | `argument N` for every command | `argument N` for an argv list; the command name alone when the audit event carries one string (Windows, `os.system`) | `subprocess.Popen` on Windows raises the event with one joined command line |
| D4 | Values are pushed at the handler phase | Values are read from `RequestInfo.scope` at the first check | A request that reaches no sink pays one dict lookup at its end |
| D5 | FNV-style keyed hash; 100 ms lock wait with takeover | `blake2b` keyed hash; a check that cannot take its entry's lock at once reports busy | An audit hook can re-enter on one thread through a finalizer or a signal handler: it must never block |

## Global Constraints

- Python `>=3.12`; runtime deps exactly `starlette` and `packaging`; `engine/` never imports `fastapi`, `starlette` or `flask`.
- Off by default. Rows exist only when `SHARPIT_AGENT_SECURITY_SINKS_REQUEST_VALUES` is true, `security-sinks` is on, and the `processes` or `files` sensor whose event carries the sink is on.
- Limits, verbatim from `RequestValues.java`: `MIN_LENGTH=4`, `MAX_LENGTH=256`, `MAX_VALUES=32`, `ENTRIES=128`, `MAX_CHECKS=256`, `MAX_SCAN=16384`, `MAX_COMPARISONS=4194304`, `HASHES=32`, `MATCHED_HASHES=8`, `MAX_SPANS=8`, `MAX_NAME=64`, `DEADLINE_SECONDS=60`, `MAX_ARGUMENTS=32`.
- `FROM_REQUEST_INPUT = "(not kept: it held request input)"`, `NOT_CHECKED = "(not kept: not checked for request input)"`.
- No value, raw path or argument in any row, log, exception text, cache or `repr`. The audit hook never raises, blocks or logs.
- Reads have no side effects. The toggle is the existing `POST {api}/java-agent/sensors/{id}` action and stays behind its gates.
- Budgets in `tests/engine/test_sensors_overhead.py` stay at 6 µs per event; a budget is never raised.
- Each ported test cites its source: `# ported: RequestValuesTests.<method>`.
- Strings in tests that look like secrets or paths follow the existing `# noqa: S108` practice. One condition per assert.
- Commits: conventional prefix, explicit paths, signed off (`git commit -s`), no AI attribution. Before each `test:` commit: `uv run python scripts/dev/red_check.py <node ids>`.
- pytest runs with `-n` set from machine load, 4 at most; overhead tests run with `-n 0`. Never the full suite locally.

## Review Focus

1. A request value equal to part of an installed package path (`?q=python`): imports are still left out, and spend none of the request's budget. (Task 4)
2. A value that arrives percent-encoded (`?f=a%2Fb`): the decoded form is what reaches the sink and must match. (Task 1)
3. A value held in the file sensor's path cache or copy list after the response: nothing keeps it. (Task 4)
4. Two concurrent requests with different values: neither matches the other's. (Task 2)
5. The host app copies or lacks `scope["route"]` (mounted app, plain Starlette, class endpoint): the sink row degrades to absent, the host call is unaffected. (Task 2)

## File Structure

| File | Responsibility |
|---|---|
| `src/sharpit/engine/sensors/sinks/__init__.py` (create) | Public interface: re-exports `RequestValues`, `Match`, `SinkMatcher`, `SecuritySinksSensor`, and the constants |
| `src/sharpit/engine/sensors/sinks/values.py` (create) | The holder: values, lifetime, bounded matching, redaction |
| `src/sharpit/engine/sensors/sinks/ownership.py` (create) | Whether the current stack is the request's own endpoint or dependency |
| `src/sharpit/engine/sensors/sinks/matcher.py` (create) | Joins request context, holder and ownership; builds sink rows |
| `src/sharpit/engine/sensors/processes.py`, `files.py` (modify) | Ask the matcher; redact their own rows; emit sink rows |
| `src/sharpit/engine/sensors/lane.py` (modify) | Build, switch and wipe the sensor |
| `src/sharpit/settings.py`, `settings_registry.py` (modify) | The setting; the journal source |
| `src/sharpit/fastapi/capture.py` (modify) | Pass the setting and context id; end the request |

---

### Task 1: Request values and bounded matching

**Files:**
- Create: `src/sharpit/engine/sensors/sinks/__init__.py`, `src/sharpit/engine/sensors/sinks/values.py`
- Test: `tests/engine/sensors/__init__.py`, `tests/engine/sensors/test_sink_values.py`

**Interfaces:**
- Consumes: `RequestInfo` from `sharpit.engine.capture.correlation` (`id`, `context_id`, `finished_ns`, `scope`).
- Produces, in `values.py`: the constants above, `Kind = Literal["command", "file"]`, and

```python
@dataclass(frozen=True, slots=True, repr=False)
class Match:
    names: tuple[str, ...]  # matched parameters, in the order held
    spans: tuple[tuple[int, int, int], ...]  # (index into the held values, start, end)
    flags: int  # F_PARTIAL=1 F_OVERFLOW=2 F_STOPPED=4 F_REPEATED=8 F_BUSY=16 F_SEEN=32
    redacted: str | None  # None when it may not cover every occurrence
    numeric: frozenset[str]  # names whose first span is a number


class RequestValues:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None: ...
    def match(self, info: RequestInfo, text: str, kind: Kind) -> Match: ...
    def end(self, request_id: str) -> None: ...
    def clear(self) -> None: ...
    def held(self) -> int: ...  # entries alive


def unchecked(match: Match) -> bool: ...  # flags & (F_STOPPED | F_BUSY | F_PARTIAL)
def keyed_hash(text: str) -> int: ...  # blake2b, per-process random key, first MAX_SCAN chars, 1..2**63-1
def valid_name(name: str) -> bool: ...  # 1..MAX_NAME chars of [A-Za-z0-9_.\-\[\]]
def fallback_name(name: str) -> str: ...  # "param#" + 4 hex digits of keyed_hash(name) & 0xFFFF
```

- [ ] **Step 1: Write the failing tests** in `test_sink_values.py`, with this helper:

```python
def info(query: str = "", path: dict[str, Any] | None = None, request_id: str = "a" * 16) -> RequestInfo:
    scope = {"query_string": query.encode(), **({"path_params": path} if path is not None else {})}
    return RequestInfo(request_id, "ctx", "GET", "/", None, 0, None, scope=scope)


def test_a_query_value_matches_until_the_request_ends() -> None:
    # ported: RequestValuesTests.aValueMatchesOnTheRequestsOwnWorkUntilTheRequestEnds
    held, request = RequestValues(), info("file=report-q3")
    assert held.match(request, "/srv/in/report-q3.pdf", "file").names == ("file",)
    request.finished_ns = 1
    held.end(request.id)
    assert held.match(request, "/srv/other/report-q3.pdf", "file").names == ()
    assert held.held() == 0


def test_a_percent_encoded_value_matches_in_its_decoded_form() -> None:
    assert RequestValues().match(info("f=docs%2Fq3+x"), "/srv/docs/q3 x", "file").redacted == "/srv/{f}"


def test_path_values_set_by_routing_after_the_first_check_are_read() -> None:
    # ported: RequestValuesTests.lateValuesAreReadAtTheFirstCheckOnceAHandlerMappingSetThem
    held, request = RequestValues(), info("a=zzzz")
    assert held.match(request, "in/quarterly", "file").names == ()
    assert request.scope is not None
    request.scope["path_params"] = {"name": "quarterly"}
    assert held.match(request, "in/quarterly", "file").names == ("name",)


@pytest.mark.parametrize(("value", "names"), [("abc", ()), ("abcd", ("v",)), ("a" * 256, ("v",)), ("a" * 257, ())])
def test_only_values_of_four_to_256_characters_are_held(value: str, names: tuple[str, ...]) -> None:
    # ported: RequestValuesTests.valuesOutsideTheLengthsAndPastTheCountAreSkippedAndCounted
    assert RequestValues().match(info(path={"v": value}), value, "file").names == names


def test_overlapping_and_repeated_spans_are_all_redacted() -> None:
    # ported: RequestValuesTests.redactionMergesOverlappingSpansAndReplacesEveryOccurrence
    match = RequestValues().match(info(path={"a": "abcd", "b": "cdef"}), "abcdef/abcd", "file")
    assert match.redacted == "{a}/{a}"


def test_a_partly_scanned_text_keeps_no_redacted_text_and_is_never_reported_repeated() -> None:
    # ported: RequestValuesTests.aPartlyScannedTextIsCheckedAgainEachTimeNeverReportedAsRepeated
    held, request = RequestValues(), info("v=needle")
    text = "x" * MAX_SCAN + "needle"
    assert [held.match(request, text, "file").flags for _ in range(2)] == [F_PARTIAL, F_PARTIAL]


def test_nine_spans_overflow_and_keep_no_redacted_text() -> None:
    # ported: RequestValuesTests.moreThanEightSpansOverflowAndKeepNoRedactedText
    match = RequestValues().match(info("v=needle"), "needle " * 9, "file")
    assert match.flags & F_OVERFLOW
    assert match.redacted is None


def test_a_busy_entry_reports_busy_and_never_waits() -> None:
    held, request = RequestValues(), info("v=needle")
    held.match(request, "warm", "file")
    with held._entries[request.id].lock:
        assert held.match(request, "needle", "file").flags == F_BUSY


def test_a_match_that_races_the_end_of_its_request_leaves_nothing() -> None:
    held, request = RequestValues(), info("v=needle")
    request.finished_ns = 1
    assert held.match(request, "needle", "file").names == ()
    assert held.held() == 0


def test_no_repr_shows_a_value_or_a_span_text() -> None:
    held, request = RequestValues(), info("v=needle")
    match = held.match(request, "needle", "file")
    assert "needle" not in repr(match) + repr(held) + repr(held._entries)
```

Also port, with the same names in snake case and their `# ported:` line: `aMissedEndIsSweptAfterTheDeadlineAndANewClaimWipesTheTable` (inject `clock`; only the deadline half, plus `clear()`), `namesThatAreNotSafeToShowAreReplacedByTheirPosition`, `theTableHoldsAtMostItsEntriesAndCountsTheRest` (129 requests, `held() == 128`), `checksStopAtTheirBudgetAndRepeatedTextsAreNotCheckedAgain`, `theComparisonBudgetStopsMatchingForTheRequest`, `signedAndDecimalNumbersAreNumbersAndNothingElseIs`. Their constants and expected flags come from the Java test bodies.

- [ ] **Step 2: Add importable stubs** returning `Match((), (), 0, None, frozenset())` and `0`, so the red is an assertion, then run `uv run pytest -q -n 4 tests/engine/sensors/test_sink_values.py`. Expected: assertion failures, no import or collection error.

- [ ] **Step 3: Implement `values.py`.** Translate `RequestValues.compare`, `add` and `redactChecked`, same order of checks. Decisions the Java does not settle:
  - Values: `parse_qsl(query.decode("latin-1"), keep_blank_values=False)` then `str(v)` of each `path_params` item, added when the key first appears in the scope. Adding path values clears the entry's remembered hashes.
  - `_entries: dict[str, _Entry]`; `_Entry` has `__slots__`, its own `threading.Lock`, no `repr` of fields. Take it with `acquire(blocking=False)` in `match`, blocking only in `end` and `clear`, which first pop the entry.
  - Insert under a table lock taken with `blocking=False` (failure: `F_BUSY`), re-check `info.finished_ns is None` after the insert and pop the entry if it is not.
  - Entries older than 60 s by `clock` are popped at the next insert. A full table returns an empty match with flags 0, as BootUI does.

- [ ] **Step 4: Run** the same command. Expected: all pass. Run `uv run pyright` and `uv run pytest -q -n 4 tests/engine/test_import_boundary.py`: clean.
- [ ] **Step 5: Commit** `feat: hold and match request values for the security-sinks sensor`.

### Task 2: Ownership by stack frame

**Files:**
- Create: `src/sharpit/engine/sensors/sinks/ownership.py`
- Test: `tests/fastapi/test_sink_ownership.py`

**Interfaces:**
- Produces: `def owned(scope: Mapping[str, Any]) -> bool`. Never raises. Reads `scope["endpoint"]` and `scope["route"].dependant` (`call`, `dependencies`) with `getattr` only.

- [ ] **Step 1: Write the failing test.** A raw ASGI middleware sets a `ContextVar` to the scope; `probe()` appends `owned(scope)` to a list. Parametrize over `base_http_middleware: bool` (a pass-through `BaseHTTPMiddleware` between the middleware and the app) and:

```python
OWN = [
    "sync",
    "async",
    "wraps_decorated",
    "dependency",
    "sub_dependency",
    "yield_dependency_exit",
    "bound_method",
    "partial",
    "nested_await",
    "starlette_function",
    "starlette_class",
]
NOT_OWN = ["gather", "create_task", "to_thread", "anyio_thread", "raw_thread", "background_task", "stream_body"]


@pytest.mark.parametrize("base_http_middleware", [False, True])
@pytest.mark.parametrize("case", OWN + NOT_OWN)
def test_only_the_endpoints_own_stack_is_owned(case: str, base_http_middleware: bool) -> None:
    seen = run_case(case, base_http_middleware)
    assert seen != []
    assert set(seen) == {case in OWN}
```

`raw_thread` captures the scope in the endpoint and passes it explicitly, since a raw thread has no context copy. Add two unit tests: `owned({})` is False; `owned({"endpoint": X, "route": Y})` where every attribute access of `Y` raises returns False.

- [ ] **Step 2: Stub `owned` as `return False`; run** `uv run pytest -q -n 4 tests/fastapi/test_sink_ownership.py`. Expected: each `OWN` case fails on its assertion.
- [ ] **Step 3: Implement.** Collect code objects of the endpoint and the dependency tree: unwrap `functools.partial`, bound methods, `__wrapped__` chains (at most 16 links), a callable instance's `type(x).__call__`, and an `HTTPEndpoint` class's handler named by `scope["method"].lower()` (`get` for `HEAD` when no `head`). Walk `sys._getframe(1)` to the root, returning True at the first frame whose `f_code` is in the set. Keep no frame or code reference after returning.
- [ ] **Step 4: Run.** Expected: all pass. Also run it under the lowest supported FastAPI and Starlette through the CI `lowest` job; a version without `dependant.dependencies` must give False, not an error.
- [ ] **Step 5: Add** `test_two_concurrent_requests_never_match_each_others_values` (two async endpoints held at an `asyncio.Barrier`, each opening a path with its own value and the other's; only its own matches through `RequestValues.match(REQUEST.get(), ...)`). Expected: pass.
- [ ] **Step 6: Commit** `feat: tell a request's own work from work it handed off`.

### Task 3: The matcher

**Files:**
- Create: `src/sharpit/engine/sensors/sinks/matcher.py`
- Test: `tests/engine/sensors/test_sink_matcher.py`

**Interfaces:**
- Consumes: Task 1 and Task 2.
- Produces:

```python
Row = Mapping[str, object]


class SinkMatcher:
    def __init__(
        self,
        context_id: str,
        on: Callable[[], bool],
        values: RequestValues | None = None,
        owns: Callable[[Mapping[str, Any]], bool] = owned,
    ) -> None: ...
    def check(self, text: str, kind: Kind) -> Match | None: ...  # None: off, internal, no request, other context
    def rows(self, kind: Kind, match: Match, text: str, target: str | None) -> tuple[Row, ...]: ...
    def request_ended(self, request_id: str) -> None: ...
    def clear(self) -> None: ...


class SecuritySinksSensor:
    name = "security-sinks"
    events: tuple[str, ...] = ()
    matcher: SinkMatcher

    def record(self, event: str, args: tuple[Any, ...]) -> tuple[Row, ...]: ...  # always ()
    def wipe(self) -> None: ...  # matcher.clear()
```

A row is exactly:

```python
{
    "source": "security-sinks",
    "kind": "command" | "file-path",
    "target": str | None,
    "parameter": str,
    "numeric": bool,
    "requestId": str,
    "rawHash": int,
    "redactedHash": int,
}  # redactedHash 0 when redacted is None
```

- [ ] **Step 1: Write the failing tests**, using `REQUEST.set(info(...))`, `owns=lambda scope: True` unless stated:
  - `test_one_row_per_matched_parameter`: `?a=alpha&b=bravo`, text `alpha/bravo`, rows' `parameter` values are `["a", "b"]` and `"alpha" not in repr(rows)`.
  - `test_no_row_for_work_the_endpoint_does_not_own`: `owns=lambda scope: False`; `check(...)` still returns the match, `rows(...) == ()`.
  - `test_a_text_seen_before_publishes_no_second_row`: same text twice, second `rows(...) == ()` while `match.redacted` is unchanged.
  - `test_nothing_is_checked_when_off_internal_outside_a_request_or_for_another_context`: four parametrized cases, `check(...) is None`.
  - `test_a_digits_only_value_is_flagged` (`# ported: RequestValuesSinksTests.aDigitsOnlyValueIsFlaggedSoTheEngineWaitsForConfirmation`): `?year=2024`, `numeric is True`.
  - `test_the_same_text_hashes_alike_and_another_value_differently`: `report-a` and `report-b` in two requests give equal `redactedHash` and different `rawHash`.
  - `test_an_owns_that_raises_publishes_nothing`: `rows(...) == ()`.
- [ ] **Step 2: Stub, run** `uv run pytest -q -n 4 tests/engine/sensors/test_sink_matcher.py`. Expected: assertion failures.
- [ ] **Step 3: Implement.** `check` order: `on()`, `INTERNAL`, `REQUEST`, `context_id`, `len(text) < MIN_LENGTH`, then the holder.
- [ ] **Step 4: Run.** Expected: all pass.
- [ ] **Step 5: Commit** `feat: build security-sinks rows from a request's own matches`.

### Task 4: The command and file sinks

**Files:**
- Modify: `src/sharpit/engine/sensors/processes.py` (`ProcessesSensor`), `src/sharpit/engine/sensors/files.py` (`__init__`, `_pair`, `_is_inner_copy_open`, `_row`, `_resolve`)
- Test: `tests/engine/sensors/test_sink_sensors.py`

**Interfaces:**
- Consumes: `SinkMatcher.check`, `SinkMatcher.rows`, `unchecked`, `FROM_REQUEST_INPUT`, `NOT_CHECKED`.
- Produces: `ProcessesSensor(matcher: SinkMatcher | None = None)`; `FilesSensor(..., matcher: SinkMatcher | None = None)` (keyword only). `None` keeps every current row byte-identical.

- [ ] **Step 1: Write the failing tests** (`run(sensor, event, *args)` sets `REQUEST` and returns the rows):

```python
def test_an_argv_argument_names_the_command_and_the_index_only() -> None:
    # ported: RequestValuesSinksTests.aCommandArgumentHoldingAValueRecordsTheCommandAndTheArgumentsIndexOnly
    rows = run(
        processes("file=report-q3"),
        "subprocess.Popen",
        "/usr/bin/convert",
        ["/usr/bin/convert", "/srv/in/report-q3.pdf", "out.png"],
        None,
        None,
    )
    assert [(r["source"], r["target"]) for r in rows] == [
        ("processes", "convert"),
        ("security-sinks", "convert, argument 1"),
    ]
    assert "report-q3" not in repr(rows)


@pytest.mark.parametrize(
    ("event", "args", "target"),
    [
        ("subprocess.Popen", ("/bin/sh", ["/bin/sh", "-c", "ls report-q3"], None, None), "sh, argument 2"),
        ("subprocess.Popen", (None, "python.exe -c pass report-q3", None, None), "python.exe"),
        ("os.system", ("convert report-q3",), "convert"),
    ],
)
def test_a_shell_or_a_joined_command_line_names_what_it_can(event: str, args: tuple[Any, ...], target: str) -> None:
    assert run(processes("file=report-q3"), event, *args)[1]["target"] == target


@pytest.mark.parametrize("argv", [["evil-tool", "--help"], "evil-tool --help"])
def test_an_executable_holding_a_value_is_named_by_neither_row(argv: object) -> None:
    # ported: RequestValuesSinksTests.anExecutableHoldingAValueIsNamedByNeitherRecord
    rows = run(processes("tool=evil-tool"), "subprocess.Popen", None, argv, None, None)
    assert [r["target"] for r in rows] == [FROM_REQUEST_INPUT, "(the executable)"]


def test_a_file_path_keeps_the_redacted_pattern() -> None:
    # ported: RequestValuesSinksTests.aFilePathHoldingAValueRecordsTheRedactedPathsPattern
    rows = run(files("name=../../etc/passwd"), "open", "reports/../../etc/passwd", "r", 0)
    assert [(r["source"], r["target"]) for r in rows] == [
        ("files", "./reports/{name}"),
        ("security-sinks", "./reports/{name}"),
    ]


def test_a_path_the_request_could_not_check_is_never_named() -> None:
    # ported: RequestValuesSinksTests.aPathLongerThanTheScanIsNeverNamedTheFirstTimeNorWhenRepeated
    sensor = files("name=quarterly")
    path = "x/" * (MAX_SCAN // 2) + "quarterly"
    assert [run(sensor, "open", path, "r", 0)[0]["target"] for _ in range(2)] == [NOT_CHECKED, NOT_CHECKED]


def test_a_path_opened_300_times_publishes_one_sink_row_and_redacts_every_file_row() -> None:
    # ported: RequestValuesSinksTests.aPathOpenedTwiceByTheRequestIsRedactedBothTimesInEveryRecord
    sensor = files("name=quarterly")
    rows = [r for _ in range(MAX_CHECKS + 44) for r in run(sensor, "open", "reports/quarterly.csv", "r", 0)]
    assert sum(r["source"] == "security-sinks" for r in rows) == 1
    assert {r["target"] for r in rows} == {"./reports/{name}.csv"}


def test_an_import_path_holding_a_value_is_left_out_and_spends_no_check() -> None:
    sensor = files("q=python")
    assert run(sensor, "open", os.path.join(sys.prefix, "python", "x.py"), "r", 0) == []
    assert sensor_values(sensor).held() == 0


def test_no_cache_keeps_a_value_after_the_request() -> None:
    sensor = files("name=quarterly")
    run(sensor, "open", "reports/quarterly.csv", "r", 0)
    run(sensor, "shutil.copyfile", "a/quarterly", "b/quarterly")  # announced, never opened
    end_request(sensor)
    assert "quarterly" not in repr(vars(sensor))


def test_not_owned_work_redacts_its_row_and_publishes_no_sink() -> None:
    rows = run(files("name=quarterly", owns=False), "open", "reports/quarterly.csv", "r", 0)
    assert [(r["source"], r["target"]) for r in rows] == [("files", "./reports/{name}.csv")]
```

Add `test_the_thirty_third_argument_is_not_checked` (`MAX_ARGUMENTS`), and `test_without_a_matcher_every_row_is_unchanged`, which replays the parametrized inputs already in `tests/engine/test_sensors_audit.py` for both sensors.

- [ ] **Step 2: Run** `uv run pytest -q -n 4 tests/engine/sensors/test_sink_sensors.py`. Expected: assertion failures (accept and ignore `matcher` first so nothing fails on the signature).
- [ ] **Step 3: Implement `processes.py`.** An argv list checks `[executable or argv[0], *argv[1:]]` up to 32 elements; index 0 targets `(the executable)`, a later one `<name>, argument N`, with `<name>` replaced by `(the executable)` when index 0 matched or was unchecked. One string is checked once: when a span starts before the end of the program's first occurrence in it, the executable held the value; otherwise the target is the program name. Element 0, or the one string, `unchecked` gives the process row `NOT_CHECKED`.
- [ ] **Step 4: Implement `files.py`.** Extract `_is_skipped(text) -> bool` from `_resolve`. In `_row`, with a matcher on: skip test first, then `check(text, "file")`, before `_seen` is read or written. A match resolves `match.redacted` through `_resolve` without caching; `redacted is None` gives `FROM_REQUEST_INPUT`; `unchecked` gives `NOT_CHECKED`, with location `elsewhere`. A placeholder goes through the mask and collapse as any path text does, as in BootUI: a letters-only name stays, a digit run in a name becomes `{n}`; the sink row's `parameter` keeps the full name. `_pending` stores `hash(text)` instead of the text.
- [ ] **Step 5: Run** the new file, `tests/engine/test_sensors_audit.py` and `tests/safety/test_w6_side_effects_safety.py`. Expected: all pass, none edited.
- [ ] **Step 6: Commit** `feat: match request values in commands and file paths`.

### Task 5: Setting, journal source, lane and request end

**Files:**
- Modify: `src/sharpit/settings.py:113`, `src/sharpit/settings_registry.py` (`JOURNAL_SOURCES`, parser map, masking notes), `src/sharpit/engine/sensors/lane.py`, `src/sharpit/engine/sensors/floor.py` (opt-in reason), `src/sharpit/fastapi/capture.py` (`_arm_sensors`, the request's `finally` after `info.finished_ns = finished`)
- Test: `tests/fastapi/test_security_sinks.py`, `tests/test_settings.py`, `tests/engine/test_sensors_audit.py`, `tests/safety/test_security_sinks_safety.py`

**Interfaces:**
- Produces: `SharpitSettings.agent_security_sinks_request_values: bool = False` (`SHARPIT_AGENT_SECURITY_SINKS_REQUEST_VALUES`, invalid value: False and a warning); `"security-sinks"` in `JOURNAL_SOURCES`; `build_lane(configured, sink, mask_path, own=(), audit=hub, *, request_values: bool = False, context_id: str = "")`; `SensorLane.request_ended(request_id: str) -> None`.
- The sensor is built only when `request_values` is true. `BUILT` and `SWITCHABLE` gain `security-sinks`. Every path that turns it off (`switch`, `pause`, `detach`) calls `wipe()`. Its toggle's `optInReason` is:

```text
Off by default: its request-value matching, which also needs SHARPIT_AGENT_SECURITY_SINKS_REQUEST_VALUES=true, holds each request's query and path values in memory while it runs.
```

- [ ] **Step 1: Write the failing tests** (reuse the `hook` fixture and `_app` helper pattern of `tests/fastapi/test_w6_audit_sensors.py`):
  - `test_off_by_default_a_request_value_in_a_path_leaves_no_sink_row`: sensors `("processes", "files", "security-sinks")` without the setting; no row, and `java-agent` lists no `security-sinks` toggle.
  - `test_an_endpoint_that_opens_a_requested_path_leaves_one_sink_row`: with the setting; `GET /read/quarterly` fires `open` from the endpoint; one row with `parameter == "name"`.
  - `test_values_are_gone_when_the_response_ends`, parametrized over a normal response, a raised exception, a client disconnect and a streaming response: `held() == 0`.
  - `test_switching_the_sensor_off_wipes_held_values_at_once`: switch from inside the endpoint; `held() == 0` before the response.
  - `test_a_background_task_and_a_streamed_body_leave_no_sink_row`.
  - `test_a_read_only_panel_refuses_the_switch` (status and body as the existing files-sensor test).
  - In the safety file: `test_a_seeded_value_reaches_no_route_log_or_error`: send a canary query value through an endpoint that opens a path, starts a command and raises; read every GET route in the console and every read tool at `MASKED` exposure. The exclusion list is the routes that already show the request itself (exchanges and the `http` journal source); the test names each one.
  - In `test_settings.py`, the row `("agent_security_sinks_request_values", "SHARPIT_AGENT_SECURITY_SINKS_REQUEST_VALUES", "maybe", False)`; in `test_sensors_audit.py`, `"security-sinks"` in the source parametrization.
- [ ] **Step 2: Run** the four files with `-n 4`. Expected: assertion failures.
- [ ] **Step 3: Implement.** In `capture.py`, `request_ended(info.id)` runs inside `_request_end_guard` immediately after `info.finished_ns` is set, and before anything that can fail.
- [ ] **Step 4: Run** the four files and `tests/fastapi/test_w6_audit_sensors.py`, `tests/engine/test_import_boundary.py`, `tests/test_code_shape.py`. Expected: all pass.
- [ ] **Step 5: Commit** `feat: wire the security-sinks sensor, off by default`.

### Task 6: Overhead, masking evidence and documentation

**Files:**
- Modify: `tests/engine/test_sensors_overhead.py`, `website/docs/settings.md:89-90`, `skills/sharpit/SKILL.md:209,229`, `plugins/sharpit/skills/sharpit/SKILL.md` (same lines), `CHANGELOG.md`, `SECURITY.md`, `AGENTS.md` (only if a path in its layout changes)
- Create: `docs/reference/matrix-updates/0.10.0-security-sinks.tsv`, `docs/decisions/<next>-request-values-in-memory.md` and its index line

- [ ] **Step 1: Extend the overhead test** with three measurements, each against 6.0e-6: processes and files with a matcher off; files with a matcher on and no request; files with a matcher on and one held 12-character value that matches nothing, over the existing hot set of 64. Run `uv run pytest -q -n 0 tests/engine/test_sensors_overhead.py`. Expected: pass. Failure is a design question: stop and report the measured numbers.
- [ ] **Step 2: Measure the capture middleware** with `/sharpit:perf-audit`, setting off and on, paired. Record the numbers in the PR body; the existing middleware budget test must pass unchanged.
- [ ] **Step 3: Masking evidence.** Dump the masking corpora on the base commit and on the branch with the setting off and diff them. Expected: byte-identical. With the setting on, every changed row is listed in the PR body.
- [ ] **Step 4: Documentation.** Settings row; the source list row; both skill files; a `SECURITY.md` paragraph stating what is held, for how long, and that matching is verbatim, not taint tracking; a changelog line; one matrix line per approved deviation; the decision file as decision, rationale and consequences.
- [ ] **Step 5: Run** `uv run pytest -q -n 4 tests/test_*.py tests/docs`, `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`. Expected: clean.
- [ ] **Step 6: Commit** `docs: describe the security-sinks sensor` and run `/sharpit:check`, `/sharpit:live-verify` (an endpoint that opens a requested path, on Windows and Linux), `/sharpit:branch-review`, then `/sharpit:llm-council --tier high`.
