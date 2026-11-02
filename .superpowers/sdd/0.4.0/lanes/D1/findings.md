# Lane D1 findings

## Finding → test → red

| Finding | Test id | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| No `dismissedFindings` section in the store (rules-only writer) | `tests/engine/advisors/test_dismissals.py::test_preserves_other_top_level_sections_across_writes` | `fbaf74e409e3537f5c5f1fb0b3238fb3235c83bd` | `AssertionError: assert '# My config\...pypi:jinja2\n' == '# sharpit co...ZW50aW9uYWw\n'` | Fixed in 2123b370068802f41a283b31c47485a6b1df9c85 |
| Finding writes not byte-stable / note not replaced | `tests/engine/advisors/test_dismissals.py::test_repeated_writes_are_byte_stable` | `fbaf74e409e3537f5c5f1fb0b3238fb3235c83bd` | `AssertionError: assert [] == [DismissedFinding(rule_id='RAPI-MAP-001', identity='v1:route=GET:/owners/{id}', note='note')]` | Fixed in 2123b370068802f41a283b31c47485a6b1df9c85 |
| `dismissed_pairs()` inert (R1) | `tests/engine/advisors/test_dismissals.py::test_dismissed_pairs_returns_rule_id_and_identity_tuples` | `fbaf74e409e3537f5c5f1fb0b3238fb3235c83bd` | `AssertionError: assert set() == {('RAPI-DOC-0...owners/{id}')}` | Fixed in 2123b370068802f41a283b31c47485a6b1df9c85 |
| `DismissedFindingsDto` keys not emitted | `tests/engine/advisors/test_dismissals.py::test_findings_dto_emits_every_key` | `fbaf74e409e3537f5c5f1fb0b3238fb3235c83bd` | `AssertionError: assert {} == {'dismissed':... 'ignored': 2}` | Fixed in 2123b370068802f41a283b31c47485a6b1df9c85 |
| Global read-only does not cover `/dismissed-findings` | `tests/engine/test_guard.py::test_dismissed_findings_global_read_only` | `bb7351f64854466cd1f85ad8badfa1222a2d65d6` | `AssertionError: assert None == Denial(status=403, body={'error': 'sharpit panel access denied', 'panel': 'dismissed-findings', 'reason': 'sharpit is read-only via SHARPIT_READ_ONLY=true'}, headers=())` | Fixed in 57fc15a40e300daafbf90433c0d5ccaece64f0d2 |
| A header set downstream (no CSP) is duplicated | `tests/engine/test_headers.py::test_security_headers_are_not_duplicated_when_downstream_sets_them` | `bb7351f64854466cd1f85ad8badfa1222a2d65d6` | `AssertionError: assert ['nosniff', 'nosniff'] == ['nosniff']` | Fixed in 57fc15a40e300daafbf90433c0d5ccaece64f0d2 |
| Overview panel still titled `Overview` (registry row) | `tests/engine/test_panels.py::test_registry_rows_0_2_0` | `bb7351f64854466cd1f85ad8badfa1222a2d65d6` | `AssertionError: assert [('overview',...lities'), ...] == [('overview',...lities'), ...]` | Fixed in 57fc15a40e300daafbf90433c0d5ccaece64f0d2 |
| Overview panel still titled `Overview` (panels report) | `tests/engine/test_panels.py::test_overview_panel_title_is_scorecard` | `bb7351f64854466cd1f85ad8badfa1222a2d65d6` | `AssertionError: assert 'Overview' == 'Scorecard'` | Fixed in 57fc15a40e300daafbf90433c0d5ccaece64f0d2 |
| No `/dismissed-findings` routes | `tests/fastapi/test_dismissed_findings_api.py::test_mvc_dismisses_lists_and_restores_a_finding_with_its_note` | `bb7351f64854466cd1f85ad8badfa1222a2d65d6` | `assert 404 == 200` | Fixed in 57fc15a40e300daafbf90433c0d5ccaece64f0d2 |
| Mutations not 403 under global read-only | `tests/fastapi/test_dismissed_findings_api.py::test_mvc_global_read_only_blocks_the_mutations_but_not_the_list` | `bb7351f64854466cd1f85ad8badfa1222a2d65d6` | `assert 404 == 403` | Fixed in 57fc15a40e300daafbf90433c0d5ccaece64f0d2 |
| Body not read as capped bytes | `tests/fastapi/test_dismissed_findings_api.py::test_mvc_reads_the_body_as_bytes_so_the_framework_never_logs_the_note` | `bb7351f64854466cd1f85ad8badfa1222a2d65d6` | `AssertionError: assert 404 == 200` | Fixed in 57fc15a40e300daafbf90433c0d5ccaece64f0d2 |
| No 415/413/409 handling | `tests/fastapi/test_dismissed_findings_api.py::test_dismissed_findings_requires_json_content_type_and_enforces_409_503` | `bb7351f64854466cd1f85ad8badfa1222a2d65d6` | `AssertionError: assert 404 == 415` | Fixed in 57fc15a40e300daafbf90433c0d5ccaece64f0d2 |
| GET list missing (no-side-effect read) | `tests/safety/test_d1_safety.py::test_get_dismissed_findings_has_no_side_effects` | `bb7351f64854466cd1f85ad8badfa1222a2d65d6` | `assert 404 == 200` | Fixed in 57fc15a40e300daafbf90433c0d5ccaece64f0d2 |
| GET list not reachable with advisor panels off | `tests/safety/test_d1_safety.py::test_get_dismissed_findings_is_allowed_with_every_advisor_panel_off` | `bb7351f64854466cd1f85ad8badfa1222a2d65d6` | `assert 404 == 200` | Fixed in 57fc15a40e300daafbf90433c0d5ccaece64f0d2 |
| Overview has no `run` (ApplicationRunDto) | `tests/engine/test_overview.py::test_overview_emits_run_metadata_and_scorecard_panel_title` | `82b7f1957192b30847b88334244cfa5f70180fd2` | `AssertionError: assert set() == {'instanceId'..., 'startedAt'}` | Fixed in f662993dd85b8f22e6b4dee57bf747933cdb3b82 |
| MCP/CLI `get_config` carries `propertySuggestions` | `tests/engine/test_tools.py::test_mcp_config_drops_only_the_property_suggestions` | `82b7f1957192b30847b88334244cfa5f70180fd2` | `AssertionError: assert [{'name': 'D1...Value': None}] == []` | Fixed in f662993dd85b8f22e6b4dee57bf747933cdb3b82 |

Messages without the `AssertionError: ` prefix are pytest's rewritten asserts whose text has no `'` (F's gate note).

## Review round 1: finding → test → red (fix `96ca0d59546beab020685032ebd4cdf40d140141`)

| Finding | Test id | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| R-D1a: REST API target with inner spaces not storable | `tests/engine/advisors/test_dismissals.py::test_dismissed_pairs_accepts_a_real_rest_api_target` | `09ee50d75fc2125cbc266fade0faafc3dd0903da` | `AssertionError: assert set() == {('RAPI-DOC-0...:list_items')}` | Fixed in bb13cc7267ca9920ee9cb94dc7ebf6c47031b0f2 |
| R-D1b: no owning-panel gate on finding mutations | `tests/fastapi/test_dismissed_findings_api.py::test_finding_mutations_need_the_owning_panel_enabled_and_writable` | `09ee50d75fc2125cbc266fade0faafc3dd0903da` | `AssertionError: assert (200, {'dismi...'ignored': 0}) == (403, {'error...ABLED=false'})` | Fixed in bb13cc7267ca9920ee9cb94dc7ebf6c47031b0f2 |
| R-D1b: test-runtime rule id accepted | `tests/fastapi/test_dismissed_findings_api.py::test_test_runtime_findings_are_refused_with_the_no_panel_message` | `09ee50d75fc2125cbc266fade0faafc3dd0903da` | `AssertionError: assert (200, {'dismi...'ignored': 0}) == (400, {'error...sharpit.yml'})` | Fixed in bb13cc7267ca9920ee9cb94dc7ebf6c47031b0f2 |
| Non-encodable / control identity answered 500 | `tests/fastapi/test_dismissed_findings_api.py::test_non_encodable_and_control_identities_are_refused_with_400_never_500` | `09ee50d75fc2125cbc266fade0faafc3dd0903da` | `assert 500 == 400` | Fixed in bb13cc7267ca9920ee9cb94dc7ebf6c47031b0f2 |
| Cache stamp taken after os.replace | `tests/engine/advisors/test_dismissals.py::test_two_stores_sharing_a_state_dir_keep_each_others_dismissals` | `09ee50d75fc2125cbc266fade0faafc3dd0903da` | `AssertionError: assert ['GHSA-aaaa-b...:pypi:jinja2'] == ['GHSA-aaaa-b...:pypi:jinja2']` | Fixed in bb13cc7267ca9920ee9cb94dc7ebf6c47031b0f2 |
| Finding rule id capped at 64 | `tests/engine/advisors/test_dismissals.py::test_a_finding_rule_id_may_be_as_long_as_a_rule_id` | `09ee50d75fc2125cbc266fade0faafc3dd0903da` | `AssertionError: assert [] == [DismissedFin...', note=None)]` | Fixed in bb13cc7267ca9920ee9cb94dc7ebf6c47031b0f2 |
| Comments in managed sections dropped / counted | `tests/engine/advisors/test_dismissals.py::test_comments_inside_the_managed_sections_are_kept_and_not_counted` | `09ee50d75fc2125cbc266fade0faafc3dd0903da` | `AssertionError: assert 1 == 0` | Fixed in bb13cc7267ca9920ee9cb94dc7ebf6c47031b0f2 |
| Full fingerprint accepted as ruleId | `tests/fastapi/test_dismissed_findings_api.py::test_a_full_fingerprint_is_not_a_finding_rule_id` | `09ee50d75fc2125cbc266fade0faafc3dd0903da` | `AssertionError: assert (200, {'dismi...'ignored': 0}) == (400, {'error...or rule id.'})` | Fixed in bb13cc7267ca9920ee9cb94dc7ebf6c47031b0f2 |
| Unowned rule's finding cannot be restored | `tests/fastapi/test_dismissed_findings_api.py::test_restoring_a_finding_whose_rule_no_advisor_owns_still_removes_its_line` | `09ee50d75fc2125cbc266fade0faafc3dd0903da` | `AssertionError: assert (400, {'error...or rule id.'}) == (200, {'dismi...'ignored': 0})` | Fixed in bb13cc7267ca9920ee9cb94dc7ebf6c47031b0f2 |
| Route splice crashes install without the anchor | `tests/fastapi/test_dismissed_findings_api.py::test_finding_routes_are_appended_when_the_dismissed_rules_anchor_is_absent` | `09ee50d75fc2125cbc266fade0faafc3dd0903da` | `assert 404 == 200` | Fixed in bb13cc7267ca9920ee9cb94dc7ebf6c47031b0f2 |
| Round 2: `_looks_like_a_note` untested (stub always False splits the identity) | `tests/engine/advisors/test_dismissals.py::test_an_identity_ending_in_a_note_token_is_refused_not_split` | `d31f06b8d5e4d756329ce69b041c5e3588180099` | `AssertionError: assert [DismissedFin..., note='Int')] == []` | Fixed in 5bd0e50c784d1fcdebb8158722837d662f54ae07 |

## Superseded reds

Not replayed by the gate: each body changed after its red commit (a space became a tab where the space was the
invalid character), so these SHAs are history only.

| Finding | Test id | Historical SHA | Reason |
|---|---|---|---|
| Notes not Base64URL round-tripped; no 400/409 validation | `tests/engine/advisors/test_dismissals.py::test_dismissed_findings_note_and_cap_validation` | `fbaf74e409e3537f5c5f1fb0b3238fb3235c83bd` | behaviour changed by R-D1a; test kept as a characterisation test (edited in `96ca0d59546beab020685032ebd4cdf40d140141`) |
| Malformed finding lines not ignored/counted/kept | `tests/engine/advisors/test_dismissals.py::test_malformed_finding_lines_are_ignored_counted_and_kept` | `fbaf74e409e3537f5c5f1fb0b3238fb3235c83bd` | behaviour changed by R-D1a; test kept as a characterisation test (edited in `96ca0d59546beab020685032ebd4cdf40d140141`) |
| Bad bodies not refused with the fixed message | `tests/fastapi/test_dismissed_findings_api.py::test_mvc_refuses_bad_bodies_with_a_fixed_message_that_never_quotes_the_note` | `bb7351f64854466cd1f85ad8badfa1222a2d65d6` | behaviour changed by R-D1a; test kept as a characterisation test (edited in `96ca0d59546beab020685032ebd4cdf40d140141`) |
| Secret note: refusal path missing | `tests/masking/test_d1_masking.py::test_a_secret_note_is_never_echoed_by_an_error` | `bb7351f64854466cd1f85ad8badfa1222a2d65d6` | behaviour changed by R-D1a; test kept as a characterisation test (edited in `96ca0d59546beab020685032ebd4cdf40d140141`) |

## Guard tests (green at red, kept as controls)

- `tests/engine/test_headers.py::test_a_response_that_sets_its_own_policy_keeps_it_whole`: assets never gain `Pragma`
  (the predict risk); a naive per-header dedup turns it red.
- `tests/safety/test_d1_safety.py::test_dismissed_findings_keep_the_guard_floor`, `::test_inactive_sharpit_hides_dismissed_findings`.
- `tests/masking/test_d1_masking.py::test_dismissed_findings_have_no_mcp_tool_or_cli_command`.

## Open findings

Open minors skipped by coordinator ruling: handoff.md "Review round 1". None else in the lane's files. One need outside the May-touch list (MCP default limit in `tool_dispatch.py`): see
`handoff.md`, "Needs from coordinator".
