# Scenario: exception-message literal scrubbing

## Coverage map

- **D3 Secret masking — active:** captured free-form exception/cause strings reach REST, request-profile, MCP/CLI, and pytest artifacts. The case concerns literal input that shape-based masking does not identify.
- **D4 Contract parity — active:** exception DTO keys and message rendering must remain stable except for named literal replacements; `METADATA_ONLY` continues omitting text and `FULL` remains verbatim.
- **D6 No side effects — active:** the new projection scrub must remain pure and must not introduce socket, filesystem, environment, or logger mutations.
- **D9 Scale and limits — active:** long exception text, regex runtime, nested causes/groups, and projection-time work need bounds.
- **D10 MCP and CLI parity — active:** these surfaces share or project exception DTOs and must not bypass scrubbed messages.
- **D1, D2 — skipped:** activation and request trust/guard behavior are outside this lane; run existing guard gates unchanged.
- **D5 — skipped:** framework introspection is not changed.
- **D7 — skipped:** the vulnerability scan is not involved.
- **D8 — skipped:** host middleware and mount integration are not changed.

## Worst-case trace

**Input:** a request raises `ValueError("invalid literal for int() with base 10: 'ordinary-sentinel-91'")` with a chained cause carrying a second sentinel, while `SHARPIT_EXPOSE_VALUES=MASKED` and `mask_secrets=false`.

1. `ExceptionStore.record` accepts ordinary `Exception` instances and calls `_record` (`src/sharpit/engine/capture/exceptions.py:326-345`).
2. `_record` splits exception-group leaves, then obtains causes with `_recorded_causes` and the main text with `_recorded_message` (`:347-371`).
3. `_recorded_causes` calls `_text` separately for every displayed cause (`:373-390`). `_recorded_message` calls `_text` for the main exception and may use `_message` for a safe host override (`:392-404`).
4. `_text` passes the exception through `error_text` and truncates only after rendering (`:305-310`). `_message` also applies `error_text` before the final `MAX_MESSAGE` cap (`:296-303`).
5. `error_text` delegates free text to `Masker.mask_text` (`src/sharpit/engine/sqltext/errors.py:470-482`). For `MASKED`, `_run_passes` returns before text patterns when `mask_secrets` is false (`src/sharpit/engine/masking.py:429-460`); an ordinary rejected integer literal matches no secret shape. The sentinel is therefore stored in the group message or cause.
6. `report`, `request_occurrences`, and `detail` expose stored dictionaries (`exceptions.py:500-545`); route, MCP, CLI and UI projections can then repeat the same value. The pytest sink also falls back to `str(exc)` when `error_text` returns empty or its mask marker (`engine/testsession/sink.py:195-213`), and its JSON/JUnit/SARIF writers consume that captured report.

**Finding:** the current shared text-mask path does not scrub this binding-literal grammar, and pytest fallback can independently stringify an exception. Projection boundaries need one shared scrub operation before any serialized output. Apply it to all free-form exception/cause message projections, but not structured A4a binding diagnostics or host logging. `FULL` must bypass it; `METADATA_ONLY` must preserve omission.

## Scenario table

| # | Dimension | Scenario | Severity | Expected behaviour | Test |
|---|---|---|---|---|---|
| 1 | D3 | CPython 3.12–3.14 `int()` rejected literal | Critical | Replace only literal with `******`; preserve grammar | Unit `test_scrubs_int_binding_literal` |
| 2 | D3 | `float()`, `strptime`, `fromisoformat`, Enum and UUID input-bearing messages | Critical | Each observed grammar hides the rejected value | Unit `test_scrubs_supported_python_binding_messages` |
| 3 | D3 | Pydantic v2 rendered `input_value`, custom message/context values | Critical | Free-form rendered exception message is scrubbed; structured diagnostics remain A4a-owned | Unit `test_scrubs_pydantic_rendered_message_only` |
| 4 | D3 | Chained `__cause__`, unsuppressed `__context__`, multiple ExceptionGroup leaves and nested groups | Critical | Every displayed main/cause message is scrubbed individually | Unit `test_scrubs_each_exception_group_and_cause_message` |
| 5 | D3 | `__notes__`, non-string `args`, and custom `repr` contain a sentinel | High | Only text actually emitted as a free-form exception/cause message is scrubbed; no wholesale traceback or repr stringification is added | Unit `test_does_not_add_notes_or_args_to_message_projection` |
| 6 | D3 | Plain arbitrary `RuntimeError("ordinary-sentinel")` message | High | Remains unchanged; this lane makes no blanket quoted-value claim | Unit `test_preserves_arbitrary_runtime_error_message` |
| 7 | D3 | Benign quoted prose, code brackets, path/identifier text, valid enum name, no-value Decimal/complex messages | High | Byte-identical output | Unit `test_preserves_binding_message_near_misses` |
| 8 | D3/D9 | Overlap with secret-shaped text and `mask_secrets=false` | Critical | Outside FULL literal scrub still applies; selected order leaves all current gate rows unchanged except named literal rows | Unit `test_scrub_mask_order_and_mask_secrets_false` |
| 9 | D4 | `MASKED`, `METADATA_ONLY`, `FULL` | Critical | MASKED scrubs; METADATA_ONLY omits; FULL preserves verbatim | Unit `test_exception_message_exposure_modes` |
| 10 | D3/D10 | Exception list/detail and request-profile REST response | Critical | No planted binding sentinel in any returned text; DTO shape unchanged | Integration `test_exception_messages_are_scrubbed_on_rest_projections` |
| 11 | D10 | MCP/CLI exception tools | Critical | Same message policy and no alternate raw projection | Integration `test_exception_messages_are_scrubbed_on_mcp_and_cli` |
| 12 | D3/D9 | Pytest sink normal capture and empty/MASK fallback; JSON, JUnit and SARIF | Critical | No sentinel in captured report or exporter; fallback invokes same scrubber | Integration `test_pytest_exception_fallback_and_exporters_scrub_messages` |
| 13 | D6 | Read exception endpoints and reports with side-effect sentinel | Critical | No socket, file mutation, logger-level change or environment mutation | Integration `test_exception_message_projection_has_no_side_effects` |
| 14 | D9 | Huge input with a pattern near the message cap | High | Bounded completion and output length remains within current limit | Unit `test_exception_scrub_is_bounded_for_huge_input` |
| 15 | D3/D4 | Delete each individual grammar replacement | High | Its named pattern test fails on the raw-literal assertion | Mutation checks for every scrub pattern |
| 16 | D3/D4 | Base-versus-branch masking corpus over real requests and every listed surface/mode | Critical | No unplanned row changes; intentional FULL and named literal deltas reviewed | Gate `scripts/dev/masking_gate.py` plus real-request JSONL review |

## Must-cover before merge (Critical + High)

- `test_scrubs_int_binding_literal`
- `test_scrubs_supported_python_binding_messages`
- `test_scrubs_pydantic_rendered_message_only`
- `test_scrubs_each_exception_group_and_cause_message`
- `test_does_not_add_notes_or_args_to_message_projection`
- `test_preserves_arbitrary_runtime_error_message`
- `test_preserves_binding_message_near_misses`
- `test_scrub_mask_order_and_mask_secrets_false`
- `test_exception_message_exposure_modes`
- `test_exception_messages_are_scrubbed_on_rest_projections`
- `test_exception_messages_are_scrubbed_on_mcp_and_cli`
- `test_pytest_exception_fallback_and_exporters_scrub_messages`
- `test_exception_message_projection_has_no_side_effects`
- `test_exception_scrub_is_bounded_for_huge_input`
- Each mutation test: deleting one pattern causes its named test to fail.
- Base/branch masking corpus gate, including row-wise direct response requests.

## Deferred (Medium + Low)

None. Python interpreter and pydantic wording is pinned only for versions supported by CI; other implementations are not claimed as covered.

## Known-issues cross-reference

Review `skills/known-issues/SKILL.md` before implementation because this is a masking change. Carry forward the spec §14/§15 decisions and do not alter A4a binding diagnostics or 422 handling.

## Next step

Scenarios written. Next: `/sharpit:plan exception-message-literal-scrubbing`, with the must-cover list as acceptance criteria.
