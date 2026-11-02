# Lane G6 Handoff

- **Lane:** `G6`
Implementer: agy gemini-4-argon-high + claude-subagent opus (resume)
- **Plan:** `docs/superpowers/plans/2026-11-01-sharpit-0.4.0/G6-gate-defaults.md`
- **Branch:** `lane/0.4.0-G6`
- **Worktree:** `C:\development\github\sharpit-wt\0.4.0-G6`
- **Base commit:** `d37c6f296da4263237b52b44ca593152a54b27d3` (`lane/0.4.0-F`)
- **Head commit:** see `git log` (evidence commit on top of 999569b2d526f8ceecb805a9bb79413206115087)

## Status

DONE — all three tasks and fix round 1 (findings 1–8) red → green; four gates below. Resumed by a Claude subagent after Antigravity hit its quota
(red 1955ea3) and the coordinator WIP-committed its edits (9dfd9e2); the WIP review is in `findings.md`.

## Commits

| Task | Red commit | Fix |
|---|---|---|
| 1 autodetect + no-app SKIPPED (F3) | 1955ea34148c685581ca5f5cf088862b79e55e05 | 9dfd9e246a80ca467c190b84807731800eaaf034 (WIP, reviewed) + b50fec7d8c53bea361a8201f20b0286e7f28b16d |
| 2 require-app + `_worst` (R14) | fe18128a907a98b04bed9192bcbe86ac8d397c5e | f0dd3519c07646ecbec722c860a715c1d6e3b8e4 |
| 3 quiet advisor notes (F4) | 04f05629ea658829f509a21991101249c7c8d2c7 | 97ccbe083e12da8d36a2539efea3a11ee240fbfa |
| Merge regression (WorkerApps unregistered after F) | see `findings.md` → Merge regression | 999569b2d526f8ceecb805a9bb79413206115087 |
| Fix round 1 (findings 1–8) | see `findings.md` → Fix round 1 | c1092bc8420a00a723fa1443d9f46ccc789c900f (+ b02b0c8 foundation test flag) |

## Interface Table

| Symbol | Module | Signature / Type | Consumers |
|---|---|---|---|
| `autodetect_apps` | `sharpit.pytest_plugin.apps` | `() -> tuple[tuple[str, object], ...]` (sorted `module:attr`) | `run_advisors`, tests |
| `select_app` | `sharpit.pytest_plugin.apps` | `(candidates: Sequence[tuple[str, object]]) -> tuple[str, object] \| None` (fix round 1: explicit branch removed) | `run_advisors` |
| `skip_reason` / `AUTODETECT` / `bare_app_run` | `sharpit.pytest_plugin.apps` | one skip formatter; evidence key `"autodetect"` marks autodetect runs | apps, terminal |
| `finding_fails` | `sharpit.engine.testsession.report` | `(finding: dict[str, Any], fail_on: str) -> bool` — the one gate-failure predicate | `write_junit`, terminal; G1G2's `fails()` should merge with it |
| `no_app_run` | `sharpit.pytest_plugin.apps` | `(names: Sequence[str], require_app: bool) -> AdvisorRun \| None` | `run_advisors`, `reconcile_workers` |
| `reconcile_workers` | `sharpit.pytest_plugin.apps` | `(parts, names, require_app, snapshot=False) -> None` | `session.pytest_sessionfinish` (controller) |
| `APPS_KEY` / `WorkerApps` | `sharpit.pytest_plugin.session` | `"sharpit_apps"` workeroutput key / controller plugin with optional `pytest_testnodedown` | registered by `session.resolve_options` |
| `app_notice` | `sharpit.pytest_plugin.terminal` | `(names: list[str] \| None, require_app: bool) -> str \| None` | `pytest_terminal_summary` |
| `PluginOptions.require_app` | `sharpit.pytest_plugin.options` | `bool = False`; `--sharpit-require-app`, ini `sharpit_require_app` | apps, session, terminal |
| `PluginOptions.verbose` | `sharpit.pytest_plugin.options` | `bool = False`; `--sharpit-verbose`, ini `sharpit_verbose`, `-vv` | terminal |
| `AdvisorRun.status` | `sharpit.engine.advisors.findings` | `Literal["PASSED", "FAILED", "UNKNOWN", "SKIPPED"]` | outcome, plugin, G1G2 |
| `_worst` | `sharpit.engine.testsession.outcome` | `FAILED > UNKNOWN > SKIPPED > PASSED`; empty → PASSED | outcome, tests |
| `state.autodetected` | plugin `_State` instance (dynamic attribute) | `list[str] \| None`: candidate names; None = autodetect did not run | apps, session, terminal |

## Red-to-Green Evidence Summary

All real reds (tasks 1–3 and fix round 1) and the superseded ones are listed in `findings.md`.

Gates at 999569b: ruff check passed; ruff format --check 416 files formatted; pyright 0 errors; pytest -n 4 3779 passed, 5 skipped, 2 failed (both overhead budgets, which also fail on the untouched base 4a47fe2 on this machine).

## Decisions

- Existing tests adapted, not weakened: three `test_plugin_inert.py` tests that pinned the 0.3.0 no-app unknown now
  pass `--sharpit-require-app` (same assertions); the two in-process ones run as subprocesses so the host test
  process's loaded modules cannot reach autodetect (6732d25).

- `_State` lives in the facade (must not touch), so the candidate list is a dynamic `state.autodetected`
  attribute read with `getattr(..., None)`. A real field would be cleaner once the facade may change.
- The controller-side hook is registered from `session.resolve_options` because the facade's
  `pytest_testnodedown` only reads `workeroutput["sharpit"]` and is outside the May-touch list.
- Autodetect is skipped when an installed (`sharpit.install`) app was snapshotted: 0.3.0 behaviour kept.
- "Notes" = findings that do not fail the gate by the JUnit predicate (dismissed or below `failOnSeverity`).
  G1G2's `fails()` (baselines) should replace `terminal._fails` when it lands.
- Under require-app the "rest-api skipped" line is not printed (nothing is skipped).

## Verification Gates

- `uv run ruff check`: All checks passed.
- `uv run ruff format --check`: 409 files already formatted.
- `uv run pyright`: 0 errors, 0 warnings.
- `uv run pytest -q -n 4` (head c1092bc): 3592 passed, 5 skipped, 0 failed
  (log `0.4.0-integration/.superpowers/sdd/0.4.0/logs/G6-pytest.log`).

## Needs from Coordinator

- Spec §11 entry: proposed text in `docs.md` (spec is outside G6's May-touch); the user-facing text is there too (O3).
- `lane_gate` red list: drop `test_explicit_app_ignores_autodetect_candidates` (deleted by ruling); three rows have
  junit messages starting `assert ...` (pytest's short form for `assert result.ret == N`), still `<failure>`
  AssertionErrors.
- Fix round 1 touched `src/sharpit/engine/testsession/report.py` (shared `finding_fails`, as the ruling asked) and
  `tests/test_foundation_suite_equivalence.py` (one flag, by ruling). G1G2 may also edit `report.py`.

## Open minors

- Worker candidates travel in `workeroutput["sharpit_apps"]` plus a controller plugin registered from
  `options.resolve` (via `session.register_worker_apps`), and live on dynamic `state.autodetected` / `state.autodetect_snapshot` attributes;
  moving them into `SessionFacts` (and a real `_State` field) is the altitude rework the review deferred.
- Mounted-child exclusion follows one route level (wrappers unwrapped); a mount nested inside a mounted app is not
  followed.
- Dismissed test-runtime findings are neither counted in `gate counts:` nor called notes.

## How to resume

Nothing left in-lane. If review asks for changes: worktree above, `export UV_LINK_MODE=copy`, targeted tests
`uv run pytest -q tests/pytest_plugin/test_plugin_gate_defaults.py tests/pytest_plugin/test_plugin_terminal.py`.
