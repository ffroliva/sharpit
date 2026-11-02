# T-swallowed-exceptions — /sharpit:predict (Task 0)

Implementer: claude-flavio opus. Personas written in turn, each without reading the others first (no subagents).

**Proposal.** During a pytest `--sharpit` session only, claim `sys.monitoring` tool id 3 or 4, subscribe globally to
`EXCEPTION_HANDLED` only, and in the callback return at once unless a test phase runs (`TEST` contextvar) and the
handler's code is application code (`is_application_frame`). For a qualifying event, locate the `try` from the
handler's entry offset (`PUSH_EXC_INFO`, first following line), parse the file once per code object with stdlib `ast`,
pick the first `except` clause that catches the exception, and record a fact when that clause is bare, `Exception` or
`BaseException` and its body neither raises nor calls a logger/`warnings`. The gate emits `sharpit.swallowed-exception`:
`HIGH` (fails the test) for `AttributeError`/`TypeError`/`NameError`/`ImportError`/`UnboundLocalError`, `INFO` (a note,
`fails()` excludes it) otherwise. The spike's `get_week_count` (`Week.week_id` missing inside `try/except Exception:
return 0`, HTTP 200 with a zero count) is the canonical case.

## Personas

1. **Architect (8/10).** The predicate is framework-free (`ast`, `types`, `linecache` only) in
   `engine/testsession/swallowed.py`; `sys.monitoring` lifecycle and pytest glue stay in `pytest_plugin/swallowed.py`.
   No dependency. Risk: `pytest_plugin/__init__.py` is outside the May-touch list, so attach/detach must ride on hooks
   that already live in `session.py` (`pytest_collection_finish` to attach, `pytest_sessionfinish` + a
   `config.add_cleanup` to detach). Mitigation: do exactly that; record it in handoff.
2. **Security (8/10).** No GET/MCP surface. Facts carry handler file, line and exception type name only: never the
   message, locals or source text (the message can hold secrets). The tool id is freed on session end and on cleanup
   after a hook error, so an interpreter left in a monitored state is the main risk. Mitigation: a lifecycle test that
   checks `sys.monitoring.get_tool(id) is None` after the session, also after a forced hook error.
3. **Contract parity (9/10).** Not BootUI behaviour; no schema change: the finding is one more `Finding` DTO row with an
   existing severity. Fingerprint semantics unchanged (severity is not part of it). Target is a cwd-relative handler
   location so a baseline survives machines.
4. **Host-app compatibility (6/10).** (a) A debugger/coverage tool owns ids 0–2; we never touch them. Ids 3 and 4 both
   taken → `attached: false` with a reason, no crash. (b) `EXCEPTION_HANDLED` cannot be `DISABLE`d per location, so
   every handled exception in the process pays one contextvar read plus a cached filename check: needs a budget
   (Task 5). (c) The handler entry instruction has no line in CPython 3.12–3.14; cleanup blocks (`COPY/POP_EXCEPT/RERAISE`)
   and `with` exits also emit the event. Mitigation: accept only offsets whose opcode is `PUSH_EXC_INFO` and that map to
   a `try` whose first clause starts on the next line; anything else is ignored (never a false positive). (d) A clause
   naming an exception that is not a builtin (`except MyError:` before `except Exception:`) cannot be resolved without
   evaluating user names: treat it as "may match" and stop (no finding).
5. **Devil's advocate (7/10).** The smaller alternative (static AST only) misses the spike: the static check cannot know
   the swallowed exception is an `AttributeError`. Legitimate broad handlers exist in green suites (`except Exception:
   return default` around optional features), which is why only programming errors fail by default. A user can relax
   with `sharpit(allow_swallowed=True)` or a baseline.

## Reconciliation

**Verdict: CAUTION, confidence 7/10.** Proceed with the mitigations: handler-entry opcode check; conservative clause
matching; facts without messages; attach/detach through `session.py` hooks plus `config.add_cleanup`; a lifecycle test
for freeing the tool id; an overhead budget for the callback. The static `FASTAPI-ERR-001` rule lives in `rules.py` as a
separate definition and check function: `RULES` stays the 20 ported rules (pinned by
`test_registry_covers_every_documented_id`), and wiring it into the advisor run needs `restapi/service.py`, which is
outside this lane's May-touch list (left for D4/the coordinator, recorded in handoff).
