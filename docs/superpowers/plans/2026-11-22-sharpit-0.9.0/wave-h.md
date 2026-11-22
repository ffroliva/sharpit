# sharpit 0.9.0 Wave H (housekeeping) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> Run `/sharpit:check` before every commit.

**Goal:** Close the 0.8.1 issues (#284, #285, #286, #288), fix the Windows session-stream flake, split
`fastapi/capture.py` below the line cap before later lanes add to it, and settle the CI scan, document and dependency
items of Wave H.

**Architecture:** One shared helper in `engine/tools04/hostloop.py` runs a tool's coroutine on the host loop and
handles a caller timeout once. It replaces four copies of that code (pentest, MySQL, PostgreSQL, Database advisor),
and H3 (#287, planned separately after its predict step) later changes which loop it picks, in that one place. The
capture split moves the exception-recording and handler-wrapping group out of `fastapi/capture.py`. `CaptureWiring`
and `CaptureMiddleware`, which refer to each other, stay in `capture.py`. No behaviour changes except #285's timeout
handling.

**Tech Stack:** Python ≥3.12, asyncio, Starlette/FastAPI, pytest + xdist, uv.

**Spec:** `docs/superpowers/plans/2026-11-22-sharpit-0.9.0/PLAN.md` (Wave H) and issues #284–#288.

## Global Constraints

- Runtime dependencies stay exactly `starlette` and `packaging`.
- Reads have no side effects; a tool timeout never leaves a single-flight lock held.
- A crash is not a red: every new test's red is an assertion that names the defect, seen with
  `uv run python scripts/dev/red_check.py <node ids>` before the fix commit.
- One condition per assert (ruff `PT018`).
- Every pytest run passes `-n`: `-n 4` at most on this machine; overhead budget tests run with `-n 0`.
- No module under `src/` passes 1000 lines; `tests/complexity_baseline.json` entries never go up.
- Overhead budgets are never raised.
- Commits: conventional prefix, explicit `git add` paths, no AI attribution.
- Work in a worktree branched from `origin/main` (`superpowers:using-git-worktrees`); never push without the
  maintainer's go.

## Review Focus

1. **The loop closes between the "is it running" check and the submit.** Expected: the tool answers its 503
   "unavailable" error, not a `RuntimeError`. Test in Task 2.
2. **The read finishes in the instant the wait times out.** Expected: the finished result is returned, not a 504 for
   work that completed. Test in Task 2.
3. **A second call arrives before the cancelled read has released its lock.** Expected: 409 busy is acceptable; the
   lock is released within one second, and a later call runs. Test in Task 2.
4. **The capture split moves a name a test monkeypatches.** Expected: every patch still intercepts the same call.
   Checked in Task 5 by making each moved patch target raise.
5. **The flake fix holds on a loaded Windows runner.** Expected: 30 consecutive passes under CPU load. Checked in
   Task 4.

---

### Task 1: Remove dead code (#284, #286)

**Files:**
- Modify: `src/sharpit/fastapi/binding_diagnostics.py:50` (delete `is_validation_error`)
- Modify: `tests/engine/test_masking_literals.py:199`

**Interfaces:** none.

- [ ] **Step 1:** Run `git grep -n is_validation_error`. Expected: only the definition at
      `binding_diagnostics.py:50`. Delete the function and any import that becomes unused.
- [ ] **Step 2:** In `test_found_at_scan_matches_what_the_lazy_pattern_matched`, replace
      `assert scrub_binding_literals(text) == _reference(text) or text == ""` with
      `assert scrub_binding_literals(text) == _reference(text)`. The `""` case is already in the parameter list, and
      both sides return `""` for it.
- [ ] **Step 3: Prove the assert still bites.** Temporarily change `scrub_binding_literals` to return `text + "x"`,
      run `uv run pytest -q -n 4 tests/engine/test_masking_literals.py -k found_at_scan`, and expect every case
      (`""` included) to fail. Revert the change.
- [ ] **Step 4:** Run `uv run pytest -q -n 4 tests/engine/test_masking_literals.py tests/fastapi/test_binding_diagnostics.py tests/fastapi/test_exceptions_api.py`
      and expect PASS. Run `git grep -n is_validation_error` and expect no output.
- [ ] **Step 5:** Commit `chore: remove the unused is_validation_error helper and a dead test clause` (closes #284,
      #286).

### Task 2: One host-loop helper and caller-timeout handling (#285)

**Files:**
- Create: `src/sharpit/engine/tools04/hostloop.py`
- Modify: `src/sharpit/engine/tools04/pentesting.py:22-37`, `mysql.py:31-40`, `postgresql.py:31-40`,
  `database_advisor.py:51-61`
- Test: `tests/engine/test_tools04_host_loop.py`

**Interfaces:**
- Produces:
  - `running_host_loop(ctx: SharpitContext) -> asyncio.AbstractEventLoop | None`: `ctx.capture.loop` when it is
    running and not closed, else `None`. H3 changes only this function.
  - `wait_on_host_loop(loop: asyncio.AbstractEventLoop, coro: Coroutine[Any, Any, T], timeout: float, timed_out: str, unavailable: str) -> T`:
    submits with `asyncio.run_coroutine_threadsafe`. On `RuntimeError` from the submit (the loop closed), it closes
    `coro` and raises `ToolCallError(unavailable, 503)`. On `concurrent.futures.TimeoutError`, it returns
    `future.result(0)` if the future is already done; otherwise it calls `future.cancel()` and raises
    `ToolCallError(timed_out, 504)`.
  - A module constant `TOOL_WAIT_TIMEOUT` in each tool module, set to today's value:
    - `pentesting`: `5.0` (exists).
    - `mysql`, `postgresql`: `READ_BUDGET + 2 * STATEMENT_TIMEOUT + 5`.
    - `database_advisor`: `SCAN_BUDGET + 2 * WALL_MARGIN + 5`.
  - The timeout messages, 504: "MySQL read timed out.", "PostgreSQL read timed out.", "Database advisor scan timed
    out.", and the pentest scan's existing "Pentesting scan timed out.".
  - The unavailable messages, 503: the pentest scan keeps "Pentesting scan is unavailable: the application's event
    loop is not running." The other three fall through to their existing no-loop path (`asyncio.run` or the
    `ASYNC_FROM_CLI` report) when `running_host_loop` returns `None`. For a loop that closes during the submit, they
    use "<MySQL read | PostgreSQL read | Database advisor scan> is unavailable: the application's event loop is not
    running."

- [ ] **Step 1: Write the failing tests** in `tests/engine/test_tools04_host_loop.py`. A fixture `host_loop` runs a
      fresh loop on a thread, sets `ctx.capture.loop`, and stops and closes the loop on teardown. The tests are
      parametrized over `(module, tool name, refresh name, OPERATION)`:
      - `sharpit.engine.tools04.mysql`, `"mysql_read"`, `refresh_mysql`, `"mysql-read"`
        (`engine/collectors/mysql/service.py:37`)
      - `postgresql`, `"postgresql_read"`, `refresh_postgresql`, `"postgresql-read"`
        (`engine/collectors/postgresql/service.py:31`)
      - `database_advisor`, `"database_advisor_scan"`, `run_scan(ctx, service)`, its `OPERATION`
        (`engine/collectors/database_advisor/report.py:29`)

      In each, the refresh is monkeypatched with an `async def` that takes the real `ctx.single_flight` lock under
      that `OPERATION`, waits on an event that is never set, and releases the lock in `finally`.

      ```python
      def test_timed_out_read_is_cancelled_and_releases_its_lock(...):
          monkeypatch.setattr(module, "TOOL_WAIT_TIMEOUT", 0.02)
          with pytest.raises(Exception) as caught:
              call_tool(CallContext(ctx, {}), tool, {}, via="mcp")
          assert isinstance(caught.value, ToolCallError)
          assert caught.value.status == 504
          assert str(caught.value) == message
          assert _released_within(ctx.single_flight, operation, 1.0)
      ```

      `_released_within` polls `try_acquire(operation)` every 10 ms. When it gets the lock, it releases it and
      returns `True`. Add these tests too:
      - `test_read_finished_at_the_deadline_returns_its_result`: drive `wait_on_host_loop` directly with a coroutine
        that has already completed and a patched future whose `result(timeout)` raises `TimeoutError` once.
        Expect the coroutine's value back.
      - `test_loop_closed_during_submit_answers_unavailable`: a loop that is closed after `running_host_loop`
        returns it. Expect `ToolCallError` with status 503, and no `RuntimeError` escaping.
- [ ] **Step 2:** Run `uv run python scripts/dev/red_check.py tests/engine/test_tools04_host_loop.py`. Expected: the
      three parametrized cases are RED at `assert isinstance(caught.value, ToolCallError)` (a bare `TimeoutError`
      today). The two helper tests fail at import (`hostloop` does not exist): they are new-code tests, not defect
      reds.
- [ ] **Step 3:** Implement `hostloop.py` per Interfaces. Replace the inline loop check and `future.result` in the four
      tool modules with `running_host_loop` and `wait_on_host_loop`. The pentest scan keeps its 503 refusal when there
      is no loop.
- [ ] **Step 4:** Run `uv run pytest -q -n 4 tests/engine/test_tools04_host_loop.py tests/engine/test_pentesting_tools.py tests/safety/test_a_database_advisor_safety.py tests/engine/collectors/mysql tests/engine/collectors/postgresql`
      and expect PASS. `test_tool_wait_is_bounded_and_releases_scan_on_timeout` stays green unchanged.
- [ ] **Step 5:** Commit the tests (`test: a timed-out database tool read is cancelled and releases its lock`) and
      then the code (`fix: cancel MySQL, PostgreSQL and Database advisor tool reads on a caller timeout`, closes
      #285). The PR body carries the `finding → test → red output` table.

### Task 3: Tests on the production code (#288)

**Files:**
- Modify: `tests/fastapi/test_capture_without_pydantic_core.py` (drop `_Store`)
- Modify: `tests/engine/test_pentesting_tools.py:90-150`

**Interfaces:**
- Consumes: `ExceptionStore.report()`. Each group has `exceptionClassName` (simple class name, for example
  `"RuntimeError"`) and `message`. The store comes from `install(FastAPI(), enabled="ON", show_banner=False).context.capture.exceptions`.
- Consumes: `pentesting_probe.run_probe(app, single_flight, root_path="")` and `pentesting_probe.OPERATION`.

- [ ] **Step 1:** In the three `..._when_pydantic_core_is_unavailable` tests, pass the installed app's real
      `ExceptionStore` and assert on `store.report()["groups"]`. Expect exactly one group. Its `exceptionClassName`
      is `"RuntimeError"` (or `"RequestValidationError"` for the validation case), its `message` is the raised
      message, and the log case's occurrence has source `"log"`. Keep one condition per assert.
- [ ] **Step 2:** In `test_tool_wait_is_bounded_and_releases_scan_on_timeout`, replace the hand-written
      acquire-and-release `action` with `lambda scope: pentesting_probe.run_probe(blocking_app, ctx.single_flight)`.
      `blocking_app` is an ASGI callable that sets `started` and then awaits `release`. The test's assertions stay
      as they are.
- [ ] **Step 3: Delete the control and re-run.**
      - Temporarily remove `release()` from `run_probe`'s `finally`. Run the pentest test and expect it to fail at the
        second call, with 409 busy instead of 504.
      - Temporarily make `ExceptionStore.record` drop the message. Run the capture tests and expect them to fail at
        the `message` assert.
      - Revert both changes.
- [ ] **Step 4:** Run `uv run pytest -q -n 4 tests/fastapi/test_capture_without_pydantic_core.py tests/engine/test_pentesting_tools.py`
      and expect PASS.
- [ ] **Step 5:** Commit `test: drive the real exception store and run_probe in two 0.8.0 tests` (closes #288).

### Task 4: The Windows session-stream flake (H5)

**Files:**
- Test: `tests/fastapi/test_claude_code_api.py:303-331`
- Modify (only if the cause is in the product): the Claude Code session watcher under
  `src/sharpit/engine/collectors/agentsessions/`

Follow `superpowers:systematic-debugging`. No retry, rerun marker, longer fixed sleep or skip.

- [ ] **Step 1: Reproduce.** On Windows, run the test 30 times in a row with `-n 0`, then 30 times under CPU load
      (another `-n 4` file set running). Record the pass count and the failing assertion, which is either the first
      `sessions`-then-`dashboard` order or the re-emission after the second file.
- [ ] **Step 2: Find the cause.** Read the stream's debounce (`SHARPIT_CLAUDE_CODE_STREAM_DEBOUNCE=50ms`) and how the
      session directory is polled or watched, against the test's fixed `asyncio.sleep(0.1)` and `asyncio.sleep(0.25)`.
      Write the cause down in one sentence, with the evidence (log lines or timestamps) that shows it.
- [ ] **Step 3a (the cause is the test's timing):** Replace both fixed sleeps with
      `await _until(lambda: <the order condition>, timeout=5.0)`. The helper polls every 20 ms and fails with the
      stream body when it times out. The assertions stay the same.
- [ ] **Step 3b (the cause is the product, for example a change the watcher misses on Windows):** Write a red test
      that names that defect, see it red with `red_check.py`, then fix the watcher.
- [ ] **Step 4:** Rerun the 30 + 30 loop from Step 1 and expect 60 of 60 passes. Run
      `uv run pytest -q -n 4 tests/fastapi/test_claude_code_api.py` and expect PASS.
- [ ] **Step 5:** Commit `test: wait on the session stream's events instead of fixed sleeps` (3a), or the `test:`
      and `fix:` pair (3b). The PR body states the cause and the 60-run evidence.

### Task 5: Split exception capture out of `fastapi/capture.py` (H9)

**Files:**
- Create: `src/sharpit/fastapi/capture_exceptions.py`
- Modify: `src/sharpit/fastapi/capture.py` (lines 128-192 and 194-360 move out)
- Modify: the importers and monkeypatch sites that name a moved function. Today these are
  `tests/fastapi/test_binding_diagnostics.py:498` (`_record_exception`),
  `tests/fastapi/test_capture_wiring.py:677` (`_mount_prefix`), the `WrappingHandlers` and `_record_logged` imports,
  and `tests/fastapi/test_capture_without_pydantic_core.py`.
- Modify if needed: `tests/complexity_baseline.json`

**Interfaces:**
- Produces: `sharpit.fastapi.capture_exceptions` owns the following. It imports `capture` only under
  `TYPE_CHECKING`, and reads the wiring through `cast("CaptureWiring | None", ctx.capture.wiring)`:
  - `_endpoint_name`, `_validation_error`, `_record_exception`, `_record_binding_exception`
  - `_template_regex`, `_mount_of`, `_mount_prefix`, `_route_template`
  - `_wrapped_key`, `_wrap_handler`, `WrappingHandlers`, `unwrap_exception_handlers`
  - `_record_logged`, `_record_logged_validation`
- `capture.py` keeps the constants, `CaptureWiring`, `CaptureMiddleware`, `wiring_of`, `several_workers`,
  `_outcome`, `_request_end_guard`, `sqlite_holder` and the rest. It calls the moved functions through the module
  (`capture_exceptions._record_exception(...)`), so each name has one patch target.
- No re-exports: importers name the new module.

- [ ] **Step 1:** Record the baseline:
      - `wc -l src/sharpit/fastapi/capture.py` (expect 908).
      - The `capture.py` entry in `tests/complexity_baseline.json` (expect 1).
      - `uv run pytest -q -n 0 tests/fastapi/test_capture_overhead.py`, with its median.
- [ ] **Step 2:** Move the functions per Interfaces, without changing any body. Then update every importer and patch
      string, which `git grep -n -E "capture\.(_record_exception|_mount_prefix|_route_template|_wrap_handler|_record_logged|WrappingHandlers|unwrap_exception_handlers)|import .*WrappingHandlers|import .*_record_logged"`
      lists.
- [ ] **Step 3: Prove each moved patch still intercepts.** For every monkeypatch that targets a moved name, make the
      patched function raise, run that test, and expect it to fail. Revert.
- [ ] **Step 4:** Verify:
      - `uv run pyright` is clean.
      - `uv run pytest -q -n 4 tests/fastapi tests/test_foundation_structure.py tests/test_foundation_split_compat.py tests/test_foundation_capture_setup.py tests/engine/test_import_boundary.py tests/test_code_shape.py`
        passes.
      - `uv run pytest -q -n 0 tests/fastapi/test_capture_overhead.py` passes, with no budget changed.
      - Both modules are under 1000 lines, and `capture.py` is about 680.
      - The sum of the complexity baseline entries for `capture.py` and `capture_exceptions.py` is no higher than
        Step 1's value. Lower an entry where a count went down; add no entry above the count that moved.
- [ ] **Step 5:** Commit `refactor: move exception capture out of fastapi/capture.py`. The PR body carries the
      before-and-after line counts, the complexity pins and the overhead medians.

### Task 6: CodeQL on pull requests into `release/**` (H6)

CodeQL runs as GitHub's default setup (`gh api repos/ffroliva/sharpit/code-scanning/default-setup`: configured,
weekly, Python, JavaScript/TypeScript and Actions). Default setup scans pull requests into the default branch and
into protected branches. `release/**` is not protected, so a release pull request into it got no scan in 0.8.0.

- [ ] **Step 1 (maintainer):** Add a branch ruleset for `release/**`. Use the minimum that makes default setup treat
      it as protected: block deletion and force-push, and require the existing CI checks. A repository setting is the
      maintainer's change.
- [ ] **Step 2:** Verify by opening a draft pull request into a `release/**` branch. Expect a `CodeQL` check on it.
- [ ] **Step 3:** In `skills/release/SKILL.md`, add a step before "open the release pull request": run the Sonar
      ratchet (`scripts/ci/sonar_ratchet.py`) and read the code-scanning alerts on the ship branch
      (`gh api repos/ffroliva/sharpit/code-scanning/alerts?ref=<branch>&state=open`). Expect zero new alerts.
- [ ] **Step 4:** Commit `docs: release skill scans the ship branch before the release pull request`.

### Task 7: Documents and tracking (H7)

**Files:**
- Modify: `ROADMAP.md` ("What is next (0.8.0)" and "After 0.7.0: Flask")
- Modify: `skills/live-verify/SKILL.md`

- [ ] **Step 1:** Rewrite `ROADMAP.md`:
      - Replace "What is next (0.8.0)" with "What 0.8.0 delivered (BootUI 2.5.0)", taken from `CHANGELOG.md`
        `[0.8.0]`.
      - Add "What is next (0.9.0)", one line per track of `PLAN.md`, Track F named as the Flask console.
      - Mark the Flask route model and gate as delivered in 0.8.0.
- [ ] **Step 2:** In `skills/live-verify/SKILL.md`, add a CLI check against the running sample:
      `uv run sharpit --url http://127.0.0.1:<port> health`. Expect a health tree with masked details. Name `--url`
      and `--api-path` (`sharpit --help`) as the only connection options, so no run uses `--api`.
- [ ] **Step 3 (with the maintainer's go):** Create milestone `0.9.0` and move #284–#288 to it with
      `gh issue edit <n> --milestone 0.9.0`.
- [ ] **Step 4:** Run `/sharpit:doc-review` on the two files. Commit
      `docs: roadmap after 0.8.0 and a CLI check in live-verify`.

### Task 8: Dependency updates (H8)

Agents never merge into `main`; Dependabot pull requests target `main`.

- [ ] **Step 1:** For each open Dependabot pull request (#198–#205), record its CI state, the upstream release notes'
      breaking changes, and whether `uv.lock` or `ui/package-lock.json` changes anything beyond the named package.
- [ ] **Step 2:** Write the table (pull request, package, from → to, CI, risk, recommendation: merge, close with a
      reason, or rebase) to `.local/0.9.0/dependabot-triage.md`, and give it to the maintainer, who merges.

## Definition of done

- [ ] Tasks 1–5 are merged through a draft pull request and `/sharpit:pr-council-review`.
- [ ] Task 6 has a `CodeQL` check on a release pull request.
- [ ] Tasks 7 and 8 are done or handed to the maintainer.
- [ ] #284, #285, #286 and #288 are closed by the merge. #287 stays open for H3.
- [ ] `/sharpit:check` is green on the branch head. No budget is raised and no ratchet goes up.
