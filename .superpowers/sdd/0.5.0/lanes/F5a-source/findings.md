# Findings: lane F5a-source

Red commit `66950d1901d481a04f97086824b1f32f89b84ef9` (10 tests, all `RED (assertion under tests/)` from
`scripts/dev/red_check.py tests/engine/test_appsource.py`, run on a clean tree checked out at that SHA; log
`0.5.0-integration/.superpowers/sdd/0.5.0/logs/F5a-source-redcheck.log`). Fix commit `7c7cd090b04aa1a1769bef74c9fd46e299224dcd`. Skeleton:
`resolve_package_root` returned `None`, `build_index` returned an empty `SourceIndex`, config unchanged (still `find_spec`).

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| appsource could import the app or follow a link out of it (spec §4.2, Review Focus 5) | tests/engine/test_appsource.py::test_appsource_never_imports_or_follows_symlinks | 66950d1901d481a04f97086824b1f32f89b84ef9 | `assert 'trap_pkg_appsource.mod' in {}` | Fixed in 7c7cd090b04aa1a1769bef74c9fd46e299224dcd |
| unbounded file count and size (spec §4.2) | tests/engine/test_appsource.py::test_bounded_files_and_size | 66950d1901d481a04f97086824b1f32f89b84ef9 | `assert 0 == 2` (`len(capped.modules)`) | Fixed in 7c7cd090b04aa1a1769bef74c9fd46e299224dcd |
| FIFO/device opened (spec §4.2, M6) | tests/engine/test_appsource.py::test_fifo_and_device_skipped | 66950d1901d481a04f97086824b1f32f89b84ef9 | `assert 'special.ok' in {}` | Fixed in 7c7cd090b04aa1a1769bef74c9fd46e299224dcd |
| parse errors crash the scan (spec §4.2, M6) | tests/engine/test_appsource.py::test_recursion_error_is_a_limitation | 66950d1901d481a04f97086824b1f32f89b84ef9 | `assert 'deep.fine' in {}` | Fixed in 7c7cd090b04aa1a1769bef74c9fd46e299224dcd |
| root from `type(app).__module__` names the framework (spec §4.2) | tests/engine/test_appsource.py::test_resolve_package_root_from_factory_app | 66950d1901d481a04f97086824b1f32f89b84ef9 | `assert None == WindowsPath('.../factory_app')` | Fixed in 7c7cd090b04aa1a1769bef74c9fd46e299224dcd |
| single-module app not scanned (spec §4.2, H7) | tests/engine/test_appsource.py::test_single_module_app_indexes_only_that_file | 66950d1901d481a04f97086824b1f32f89b84ef9 | `assert None == WindowsPath('.../solo_app.py')` | Fixed in 7c7cd090b04aa1a1769bef74c9fd46e299224dcd |
| `__main__` app silently skipped (spec §4.2, H7) | tests/engine/test_appsource.py::test_main_module_app_not_scanned_with_reason | 66950d1901d481a04f97086824b1f32f89b84ef9 | `assert 0 == 1` (`len(reasons)`) | Fixed in 7c7cd090b04aa1a1769bef74c9fd46e299224dcd |
| `app_package` through `find_spec` imports parents (spec §4.2, Review Focus 5) | tests/engine/test_appsource.py::test_app_package_setting_never_imports | 66950d1901d481a04f97086824b1f32f89b84ef9 | `assert None == WindowsPath('.../loaded_pkg_appsource')` | Fixed in 7c7cd090b04aa1a1769bef74c9fd46e299224dcd |
| config had its own root resolver (spec §4.2, H5) | tests/engine/test_appsource.py::test_config_uses_the_one_resolver | 66950d1901d481a04f97086824b1f32f89b84ef9 | `assert [] == ['cfg_app_appsource.main']` | Fixed in 7c7cd090b04aa1a1769bef74c9fd46e299224dcd |
| source index retained after the scan (spec §4.2, M5) | tests/engine/test_appsource.py::test_source_index_not_retained_after_scan | 66950d1901d481a04f97086824b1f32f89b84ef9 | `assert 0 == 1` (`len(refs)`: config never built a `SourceIndex`) | Fixed in 7c7cd090b04aa1a1769bef74c9fd46e299224dcd |

## Mutations (each rule removed in a scratch worktree at the fix SHA, outside the lane worktree)

Run: `tests/engine/test_appsource.py tests/engine/config` against the mutated `src`.

| Rule removed | Failing tests |
|---|---|
| `S_ISREG` check | `test_fifo_and_device_skipped` |
| `max_file_bytes` check | `test_bounded_files_and_size`, `config/test_getenv_scan.py::test_corpus` |
| `max_files` check | `test_bounded_files_and_size` |
| parse errors caught (only `OSError` kept) | `test_recursion_error_is_a_limitation`, `test_corpus` |
| holder lookup replaced by `type(app).__module__` | `test_resolve_package_root_from_factory_app`, `test_single_module_app_indexes_only_that_file`, `test_main_module_app_not_scanned_with_reason` |
| `__main__` check | `test_main_module_app_not_scanned_with_reason` |
| single-module file resolution | `test_single_module_app_indexes_only_that_file` |
| single-file root walks its directory | `test_single_module_app_indexes_only_that_file` |
| config back on `find_spec` | `test_config_uses_the_one_resolver`, `test_source_index_not_retained_after_scan`, 5 config report tests |
| config caches the `SourceIndex` | `test_config_uses_the_one_resolver`, `test_source_index_not_retained_after_scan` |
| unloaded `app_package` through `find_spec` | `test_app_package_setting_never_imports` (+ 6 config tests) |
| all three link defences (entry `is_symlink`/`is_junction`, entry containment, `_add` containment; fix round 1 merged the last two into one realpath per entry, council-claude #8) | `test_appsource_never_imports_or_follows_symlinks` (`assert 'trap_pkg_appsource.jlink.o' not in ...`) |
| any ONE link defence alone | nothing fails: the other two still hold (defence in depth, by design; recorded, not a gap) |

## Pins

None: every lane test was red at the red SHA.

## Fix round 1 (council-claude.md, council-gptoss.md, review-gemini-r1.md)

Red commit `7ff18edae1a3534b17e5c929be137e2bfe1bab34` (7 tests, all `RED (assertion under tests/)` from `red_check.py` at that SHA; log
`logs/F5a-source-redcheck-r1.log`). Fix commit `ea1cf6541ca4dc2f3e04b8842cf0f99d9064d73a`. A first version of the red commit (`2f55f98`, never
reviewed or recorded) crashed one test on Windows MAX_PATH (40 nested dirs); it was amended to 40 sibling dirs
before any record, so `2f55f98` is not an ancestor of the head.

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| council-claude #1 (high): a `__main__` re-export hides the real package | tests/engine/test_appsource.py::test_main_reexport_resolves_the_real_package | 7ff18edae1a3534b17e5c929be137e2bfe1bab34 | `assert None == WindowsPath('.../myapp')` | Fixed in ea1cf6541ca4dc2f3e04b8842cf0f99d9064d73a |
| council-claude #1 (high): `python -m pkg` app not resolved | tests/engine/test_appsource.py::test_python_dash_m_package_resolves | 7ff18edae1a3534b17e5c929be137e2bfe1bab34 | `assert None == WindowsPath('.../myapp')` | Fixed in ea1cf6541ca4dc2f3e04b8842cf0f99d9064d73a |
| council-claude #1 (high): `app_package` cannot override autodetect | tests/engine/test_appsource.py::test_app_package_beats_autodetect | 7ff18edae1a3534b17e5c929be137e2bfe1bab34 | `assert WindowsPath('.../other_pkg') == WindowsPath('.../mine_pkg')` | Fixed in ea1cf6541ca4dc2f3e04b8842cf0f99d9064d73a |
| council-claude #1 (high): `app_package` cannot fix a script `__main__` | tests/engine/test_appsource.py::test_app_package_overrides_a_script_main | 7ff18edae1a3534b17e5c929be137e2bfe1bab34 | `assert None == WindowsPath('.../myapp')` | Fixed in ea1cf6541ca4dc2f3e04b8842cf0f99d9064d73a |
| council-claude #2 (medium): wall budget only checked at .py files | tests/engine/test_appsource.py::test_wall_budget_checked_per_directory_entry | 7ff18edae1a3534b17e5c929be137e2bfe1bab34 | `assert False is True` (`index.truncated`) | Fixed in ea1cf6541ca4dc2f3e04b8842cf0f99d9064d73a |
| council-claude #3 (medium): failed files do not count toward max_files | tests/engine/test_appsource.py::test_unparsable_files_count_toward_max_files | 7ff18edae1a3534b17e5c929be137e2bfe1bab34 | `assert False is True` (`index.truncated`) | Fixed in ea1cf6541ca4dc2f3e04b8842cf0f99d9064d73a |
| review-gemini #1 (minor): no post-read size check | tests/engine/test_appsource.py::test_file_grown_past_the_size_bound_after_stat | 7ff18edae1a3534b17e5c929be137e2bfe1bab34 | `assert 'grown.grown' not in {...}` | Fixed in ea1cf6541ca4dc2f3e04b8842cf0f99d9064d73a |

Mutation: each rule removed is exactly the red state above (the fix adds one rule per test); reverting `ea1cf6541ca4dc2f3e04b8842cf0f99d9064d73a` in
`src/` alone makes all seven fail again (the red replay).

Not fixed, with reason:
- council-gptoss "`entry.is_junction()` does not exist": rejected by the coordinator (`os.DirEntry.is_junction` exists on 3.12+; the junction test runs it on Windows).
- council-gptoss low "limitation strings leak path handling": limitations are not part of any report today; advisor lanes mask them at the core's output boundary (spec §4.3).
- council-gptoss low "non-str `sys.path` entries": skipped by `_search` by design (typed `Sequence[object]`); not worth a test.
