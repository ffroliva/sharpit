---
type: retrospective
date: 2026-11-16
tags: [sharpit, cli, architecture, import-boundary, testing]
---

# The CLI import boundary: three review rounds before the rule bit

## Outcome

Task 1 of `docs/superpowers/plans/2026-11-16-sharpit-cli.md` is merged into the integration branch `feat/sharpit-cli`
(merge `9831cdb1`, then `cd59b3c3`). `tests/engine/test_import_boundary.py` and `AGENTS.md` architecture rules 2 and 4
now state and enforce:

- no module outside `sharpit/cli/` imports `sharpit.cli`, checked over the whole package (the plan named `engine/`,
  `fastapi/` and `pytest_plugin/`; the whole-tree form is stricter and has no violation today);
- modules under `sharpit/cli/` import only the standard library and `sharpit.cli`, not even under `TYPE_CHECKING`;
- `sharpit/cli/client.py` is the one CLI module allowed `urllib.request` and `http.client`.

The safety model is unchanged.

## Worked

- Planting a violation in the real source tree, running the real-tree test, and seeing it fail on an assertion before
  restoring the file. It confirmed that `import sharpit.cli` in `fastapi/install.py` and `from sharpit import
  __version__` in `cli/` are both caught.
- Mutating the rule in memory (a bare prefix match, a skipped `TYPE_CHECKING` block, a smaller standard-library set)
  and checking that a named test fails. One surviving mutant, `_within` as a bare prefix, led to the witness
  `import sharpit.cli_extra` (`cd59b3c3`).
- Comparing every full-suite failure against the base before acting: the masking failure and two overhead budgets were
  load, not the change.

## Didn't work

| What | Root cause | Mechanism now in place |
|---|---|---|
| The first version declared that `fastapi/` and `pytest_plugin/` never import `sharpit.cli`, but only a test on a planted temporary tree exercised it | `adapter_violations` scans `engine/` only, and on `fastapi/` it reports the package's own imports | A real-tree `== []` test plus a planted test through the same default-root path for each rule (`test_cli_import_boundaries_hold_on_the_real_tree`, `test_nothing_outside_the_cli_imports_it`) |
| The outward rule was first a deny-list and missed `from sharpit import install`, `sharpit.settings`, `sharpit.report` and third-party HTTP libraries | A deny-list names the known modules; transitive engine imports and new libraries pass | An allow-list: the standard library and `sharpit.cli` only (`cli_dependency_violations`) |
| A sentence added to safety model item 6 to answer a review finding was read as weakening it | Safety-model wording was changed inside a review-fix round | Reverted; the wording moves to the documentation task with `/sharpit:predict` and `/sharpit:llm-council --tier high`, as `AGENTS.md` requires |
| A full local suite run looked like a crash: every xdist worker "node down", no summary | The run was wrapped in a 30-minute shell timeout and was stopped at exactly 1800 s; under memory pressure the suite takes about an hour | Full local runs carry no outer timeout shorter than the suite; `pytest-timeout` is the per-test hang guard; a crashed worker's test is rerun alone on branch and base |
| `uv sync` in a new worktree failed with os error 1142 | The NTFS hard-link limit on a file in the uv cache | `UV_LINK_MODE=copy` for syncs in new worktrees |

## Decisions

- The inward rule covers the whole `sharpit` package instead of three subpackages. Rationale: the narrower form left
  `sharpit/__init__.py`, `report/` and the settings modules unchecked. Consequence: any future import of the CLI from
  the package fails the gate.
- The CLI may import only the standard library and itself. Consequence: `--version` reads the installed version with
  `importlib.metadata` instead of importing `sharpit`.
- `http.client` is allowed in `sharpit/cli/client.py` alongside `urllib.request`. Rationale: the client must catch
  `http.client.HTTPException` (for example `BadStatusLine` from a non-HTTP port) to report it as a message.

## Open

- The wording of safety model item 6, the "no read MCP or CLI tool may open a socket" constraint (server-side tools),
  and `SECURITY.md` on outbound requests, for the documentation task.
- A full green run of the merged tree: locally under memory pressure, 15,171 passed and 4 failed. The masking failure
  was a per-test timeout and passes alone on branch and base. Paired `-n 0` runs of the three overhead budgets on a
  loaded machine (1.5 GB free memory) failed on both sides: the sensors budget 3 of 3 on the base and 1 of 2 on the
  branch, the SQL statement budget 1 of 3 on the base and 2 of 2 on the branch. The lockfile, Python, SQLAlchemy and
  Starlette versions are identical, and the only `src/` difference is a docstring-only `sharpit/cli/__init__.py` that
  nothing imports at run time. The budgets remain unverified until a quiet-machine pair or CI runs.
- The scanner does not see `importlib.import_module` or `__import__`, and the allow-list admits network-capable
  standard-library modules that are not gatekept (`asyncio`, `ftplib`, `xmlrpc.client`). Both limits predate this change.
