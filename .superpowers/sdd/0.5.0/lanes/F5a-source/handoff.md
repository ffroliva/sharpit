# Handoff: lane F5a-source (sharpit 0.5.0)

Implementer: Claude Code subagent / Claude Opus 5.5 (claude-opus-5-5)
Branch `lane/0.5.0-F5a-source`, from `release/0.5.0` @ 836d3fd. Plan:
`docs/superpowers/plans/2026-11-03-sharpit-0.5.0/F5a-foundation.md` (F5a-source Task 2; Task 1 council is the
coordinator's, on this diff). Spec §4.2, §14.

## Status

DONE: Task 2 (red `66950d1901d481a04f97086824b1f32f89b84ef9`, fix `7c7cd090b04aa1a1769bef74c9fd46e299224dcd`, evidence commit after). Next step: coordinator council
(`/sharpit:llm-council --tier high` on §4.2 → `council.md`), review, lane gate.

## Reds

All ten in `findings.md` (table with `Red SHA`); every one `RED (assertion under tests/)` at `66950d1901d481a04f97086824b1f32f89b84ef9`.

| Must-cover test | Exists | Passes at head |
|---|---|---|
| tests/engine/test_appsource.py::test_appsource_never_imports_or_follows_symlinks | yes | yes |
| tests/engine/test_appsource.py::test_single_module_app_indexes_only_that_file | yes | yes |
| tests/engine/test_appsource.py::test_main_module_app_not_scanned_with_reason | yes | yes |
| tests/engine/test_appsource.py::test_app_package_setting_never_imports | yes | yes |
| tests/engine/test_appsource.py::test_config_uses_the_one_resolver | yes | yes |
| tests/engine/test_appsource.py::test_source_index_not_retained_after_scan | yes | yes |

## Consumer interface (what advisor lanes use)

| Symbol | Use |
|---|---|
| `appsource.resolve_package_root(app, modules, *, app_package=None, search_path=(), reasons=None) -> Path \| None` | The one resolver. Pass the app object and `sys.modules`; the shortest-named loaded module whose `vars()` holds the app wins, else `app_package`. Returns the TOP-LEVEL package directory, or the `.py` file for a single-module app. `None` appends a reason to `reasons` (`__main__` app, nothing holds the app, package not imported). `search_path`: on-disk lookup (stat only) for names not in `modules`; only config passes it (see decision 2) |
| `appsource.build_index(root, *, max_files=2000, max_file_bytes=524288, wall_budget_s=10.0, thread=True) -> SourceIndex` | Worker thread + wall budget (the join waits budget + 1 s; a stuck file gives an empty, `truncated` index with a limitation). `thread=False` runs on the caller's thread (config only) |
| `SourceIndex(modules: dict[str, ModuleInfo], limitations: list[str], truncated: bool)` | Do not cache it; cache only the report built from it (spec §4.2) |
| `ModuleInfo(name, path, tree, imports, functions)` | `name` dotted from the root's parent (`pkg/a/__init__.py` → `pkg.a`); `imports` absolute names, relative ones resolved, climbing out dropped; `functions` every def/async def name in walk order |
| `appsource.GetenvFinding`, `getenv_findings(tree, location)`, `scan_packages(roots)` | getenv/secret detection from the engine (spec §5: never from `collectors/config`) |
| `appsource.MAX_FILES`, `MAX_FILE_BYTES` | defaults; advisor lanes pass `settings.architecture_max_files` / `architecture_max_file_bytes` |

## Decisions (nobody to ask; recorded here)

1. **Config reads on the caller's thread** (`build_index(..., thread=False)`): the spec §14 exemption is enforced by
   `tests/conftest.py::_exempt_caller`, which walks the reading thread's frames for `sharpit.engine.collectors.config`.
   A worker thread has no config frame, so the shared GET/MCP sweeps would report config's read. Config's scan was
   on the request thread in 0.3.0 too; the per-file deadline still bounds it.
2. **Explicit `config_scan` names are also looked up on `sys.path`** (`search_path=sys.path`, stat calls only,
   never an import, never `find_spec`, no `sys.path_importer_cache` write). Existing tests
   (`test_config_report.py`: `test_secret_default_masked`, `test_getenv_suggestions_and_metadata_on_set_keys`,
   `test_config_get_no_side_effects`, ...) configure packages that are on `sys.path` but never imported, which
   0.3.0's top-level `find_spec` found. `app_package` and the default (`config_scan=True`: `app_package`, else the
   install() caller module) resolve through `sys.modules` only, as spec §4.2 says.
3. **Undecodable bytes are replaced, not a limitation**: the file is read as bytes (bounded), the encoding taken from
   `tokenize.detect_encoding`, decoded with `errors="replace"`. `config/test_getenv_scan.py::test_corpus` (import path
   only may change) expects a finding in a file with stray `\xff\xfe` bytes, as 0.3.0 did. `UnicodeDecodeError`
   (a `ValueError`) and a bad coding cookie (`SyntaxError`/`LookupError`) are still limitations.
4. **Resolver returns the top-level package** for both the holder module and `app_package` (0.3.0 config did the
   same); a lane that needs a sub-package filters `SourceIndex.modules` by prefix.
5. **Behaviour change**: a single-module app (`main.py`) is now scanned by config (0.3.0 skipped it), per spec §4.2.
6. **Size bound 512 KiB** (was 1 MB in the 0.3.0 getenv scan), per spec §4.2.
7. Skipped directories kept from 0.3.0: `.venv`, `venv`, `node_modules`, `__pycache__`, `site-packages`.
8. `getenv_findings` split (`_os_aliases`) to stay under C901, so `tests/complexity_baseline.json` only loses the
   `getenv_scan.py: 1` entry (total down by 1), with no entry for `appsource.py`.

## Questions for the coordinator

1. Spec §14 (outside May-touch): append rows for decision 2 (`config_scan` names found on `sys.path` without import)
   and decision 3 (undecodable bytes replaced) if you agree.
2. `tests/test_side_effect_guard.py::test_side_effect_guard_allows_config_getenv_scan` and
   `tests/scripts/test_lane_gate.py::GETENV_SCAN` still name `collectors/config/getenv_scan` as plain strings (a fake
   frame name and a baseline key in a fixture); both pass and are outside May-touch. Rename when convenient.

## Gates

At `7c7cd090b04aa1a1769bef74c9fd46e299224dcd` (Windows, Python 3.13.7): `ruff check` clean; `ruff format --check` clean; `pyright` 0 errors.
Full `pytest -q -n 4`: 4661 passed, 9 skipped, 3 failed, 2 errors in 15:55
(`0.5.0-integration/.superpowers/sdd/0.5.0/logs/F5a-source-pytest.log`). None from this lane:
the 2 errors (`vulns/test_osv.py`, `vulns/test_epss.py` teardown: "cwd changed: .../lanes/F5a-source/field-map.md",
"checklist.md") were my evidence files written into the worktree during the run; 2 failures were overhead budgets
under load ("within the noise: suspect a busy machine"); `test_every_budget_module_runs_last` hit an xdist conftest
name collision (`cannot import TIMING_MODULES from tests/fixtures/apps/unbounded_read/conftest.py`). Rerun of those
five files serially: **149 passed** (`logs/F5a-source-rerun.log`). Budgets untouched.

## How to resume

`git log --oneline release/0.5.0..HEAD` in the worktree; the lane is complete pending council and review.
