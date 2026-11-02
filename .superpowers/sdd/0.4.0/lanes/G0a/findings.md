# G0a findings

| test id | Historical SHA | assertion message |
|---|---|---|
| tests/test_sanitize_golden.py::test_sanitize_golden_scrubs_2_2_0_volatile_keys_and_secrets | b6b1a4e | AssertionError: assert 'a1b2c3d4-real' == '00000000' |
| tests/test_sanitize_golden.py::test_sanitize_golden_writes_captured_tree_and_meta_without_touching_nullable | b6b1a4e | AssertionError: assert False + where False = is_file() (overview/captured.json not written) |
| tests/test_conformance.py::test_golden_capture_manifest_has_all_2_2_0_panels_and_no_error_envelopes | b6b1a4e | AssertionError: assert False + where False = is_file() (2.2.0/meta.json missing) |
| tests/test_conformance.py::test_conformance_2_2_0_goldens_and_ids_mapping | b6b1a4e | AssertionError: assert [] (no captured fixtures) |

Fix commit: 932df69 (`feat(goldens): sanitise BootUI 2.2.0 captured golden fixtures`).
`test_golden_2_2_0_fixtures_hold_no_secrets` is a guard, not a red (it passes vacuously before the fixtures exist).

## Findings during capture

- Self-parity of a raw capture fails under F's loader: items after the first carry `null` where item 0 has a value
  (e.g. `activity entries[].detail`). Fix in the sanitiser, not the loader: 2.2.0 goldens are reduced to one merged
  representative item per list (`shape_golden`). Panel lanes still own `nullable.json`.
- tiny-ledger's `management.endpoints.web.exposure.include=health` leaves beans/loggers/mappings empty; the app was run
  with `--management.endpoints.web.exposure.include=health,info,beans,conditions,configprops,env,loggers,mappings,metrics,startup,scheduledtasks`
  (a run argument only; the reference repo is untouched).
- BootUI's POSTs need Spring Security's CSRF pair (`XSRF-TOKEN` cookie + `X-XSRF-TOKEN` header), not a BootUI token.
- Embedded absolute Windows paths (`file [C:\...]` in beans `resource`) are now replaced with `/path`.

## Fix round 1 (resumed worker, Implementer: claude-subagent sonnet)

Ruling: one item per distinct shape (supersedes the merged-representative decision; the first four reds below are historical).

| test id | Red SHA | assertion | Disposition |
|---|---|---|---|
| tests/test_sanitize_golden.py::test_sanitise_keeps_urls_and_scrubs_embedded_paths | 0aef2519e88a27643f49a11ebb188e6408b86c33 | assert ['jdbc:postgr...lasspat/path'] == ['jdbc:postgr...hangelog.xml'] (URL mangled) | Fixed in d65d77c2238d4160ee8c3b4801eb1275a05684e3 |
| tests/test_sanitize_golden.py::test_sanitise_scrubs_more_2_2_0_epoch_fields_and_keeps_nulls | 0aef2519e88a27643f49a11ebb188e6408b86c33 | assert {'capturedAt'...Seen': 8, ...} == {...00000000...} (epoch fields not normalised) | Fixed in d65d77c2238d4160ee8c3b4801eb1275a05684e3 |
| tests/test_sanitize_golden.py::test_shape_golden_keeps_one_item_per_distinct_shape_and_real_nulls | 0aef2519e88a27643f49a11ebb188e6408b86c33 | assert [{'v': 'a'}] == [{'v': 'a'}, {'v': True}] | Fixed in d65d77c2238d4160ee8c3b4801eb1275a05684e3 |
| tests/test_sanitize_golden.py::test_main_refuses_a_secret_that_only_shows_before_shaping | 0aef2519e88a27643f49a11ebb188e6408b86c33 | assert False (secret written) | Fixed in d65d77c2238d4160ee8c3b4801eb1275a05684e3 |
| tests/test_sanitize_golden.py::test_main_refuses_error_envelope_bodies | 0aef2519e88a27643f49a11ebb188e6408b86c33 | assert False (error body written) | Fixed in d65d77c2238d4160ee8c3b4801eb1275a05684e3 |
| tests/test_sanitize_golden.py::test_main_writes_captured_tree_and_keeps_nullable_and_provisional | 0aef2519e88a27643f49a11ebb188e6408b86c33 | assert ValueError('source must be under replica/evidence ...') is None (tmp_path layout refused) | Fixed in d65d77c2238d4160ee8c3b4801eb1275a05684e3 |
| tests/test_sanitize_golden.py::test_main_layout_follows_the_source_folder_name | 0aef2519e88a27643f49a11ebb188e6408b86c33 | assert ValueError('source must be under replica/evidence ...') is None | Fixed in d65d77c2238d4160ee8c3b4801eb1275a05684e3 |

Fix commits: d65d77c, 1defc69 (error guard keeps the null `error` DTO field of http-probe; rejects any set root `error`), fixtures regenerated in ea5fd9e.
Regenerate: `python scripts/sanitize_golden.py replica/evidence/2.2.0 tests/fixtures/bootui/2.2.0 nested` (layout also auto-detected from the folder name).
