# Task 3: Docs site design tokens

## TDD evidence

- Added four docs theme tests and committed them first as `4bb6695` (`test: docs site reads the shared tokens`).
- `red_check.py` reported all four new node IDs as `RED (assertion under tests/)`; there were no collection or import errors.
- The focused verification `uv run --no-sync pytest -q tests/design tests/test_shard.py tests/test_ci_layout.py` passed: 55 passed, 5 existing pytest-asyncio deprecation warnings.
- `uvx --python 3.12 --with-requirements requirements.txt mkdocs build --strict` exited 0.

## Browser matrix

Headless Chromium served the built site at `/sharpit/`. For each OS preference, the default scheme was observed, the other palette position was selected with Material's toggle, and the selected scheme was checked after an instant navigation to the MCP docs page.

| OS preference | Palette | Header background | Page background | Link color | Link contrast | Heading weights | Scheme survived navigation |
|---|---|---|---|---|---:|---|---|
| Light | Light (`default`) | `oklch(0.965 0 0)` | `oklch(1 0 0)` | `oklch(0.53 0.124 60)` | 5.49:1 | 400 / 600 | Yes |
| Light | Dark (`slate`) | `oklch(0.205 0 0)` | `oklch(0.17 0 0)` | `oklch(0.78 0.13 65)` | 9.30:1 | 400 / 600 | Yes |
| Dark | Light (`default`) | `oklch(0.965 0 0)` | `oklch(1 0 0)` | `oklch(0.53 0.124 60)` | 5.49:1 | 400 / 600 | Yes |
| Dark | Dark (`slate`) | `oklch(0.205 0 0)` | `oklch(0.17 0 0)` | `oklch(0.78 0.13 65)` | 9.30:1 | 400 / 600 | Yes |

Observed page headings used weights 400 (h1/h2) and 600 (h3). No headings outside those weights were present.

## Other gates

- Repo-wide Ruff: passed.
- Ruff format check: passed (711 files already formatted).
- Strict Pyright: 0 errors, 0 warnings, 0 informations.
- Full pytest (`uv run --no-sync pytest -q -n 8`): 5,974 passed, 28 skipped, 7 failed, 160 errors, 98 warnings in 724.79s. The errors include the side-effect fixture reporting the in-repo log files `task-3-full-pytest.log` and `task-3-codex.log` as unexpected cwd changes. The isolated `tests/engine/config/test_config_report.py::test_config_get_no_side_effects` passed when run without writing output into the repo.
- The seven failures were that side-effect check, a crashed xdist worker on `tests/test_masking_corpus.py::test_a_harmless_value_that_shares_hex_with_the_sentinel_is_not_a_leak`, and five overhead budget checks. The overhead failures showed busy-machine noise, so they are not reliable measurements from this shared run.

## Deviations and cleanup

- The CUA browser host was unavailable, so the browser matrix ran in headless Chromium using the existing Playwright install in `ui/node_modules`; no dependency was added.
- Material rendered links in its default muted color despite the custom palette variable, so `sharpit.css` sets the link selector directly to `--accent`.
- The CSS copy matched `design/tokens.css` byte-for-byte on Windows, so `.gitattributes` needed no change.
- Static server port 8013 was stopped and released with `agentctl` after browser verification.
- The repo-wide pytest log was initially written under `.superpowers/` inside the repo; the no-side-effect fixture detected it. Its representative isolated node passed without that in-repo output file. Full pytest was not rerun because this full suite took 12 minutes and the shared run also had noisy performance measurements and an xdist worker crash.
