---
type: retrospective
date: 2026-11-16
tags: [sharpit, cli, architecture, import-boundary, testing]
---

# CLI import boundary

## Outcome

Commits `9831cdb1` and `cd59b3c3` establish the whole-package inward rule and an outward CLI import rule. The scanner
checks imports from every module under `src/sharpit/`, and the CLI rule is tested against both the source tree and
planted modules. The CLI standard-library allow-list is explicit and version-independent. `sharpit/cli/client.py`
remains the only CLI module allowed to import `urllib.request` and `http.client`. CLI modules may import
`__version__` from `sharpit`.

## Decisions

| Decision | Rationale | Consequence |
|---|---|---|
| Scan the whole `src/sharpit/` tree for imports of `sharpit.cli`. | A rule limited to selected packages leaves the package root, reports and settings unchecked. | Any module outside `sharpit/cli/` that imports the CLI fails the real-tree boundary test. |
| Name permitted standard-library modules explicitly in `CLI_STDLIB`. | A runtime-derived stdlib set varies by Python version and admits modules with network or process capabilities. | A new CLI standard-library dependency requires an explicit reviewed allow-list entry. |
| Keep `http.client` in `sharpit/cli/client.py`. | The client classifies protocol exceptions such as `BadStatusLine` as user-facing transport errors. | The gatekeeper limits both `http.client` and `urllib.request` to the client file. |
| Permit `__version__` from `sharpit` in CLI modules. | The CLI needs the package version without importing its adapter-bearing package surface. | Other names from `sharpit`, and a bare `import sharpit`, remain violations. |

## Lessons

- A boundary rule requires a real-tree test and a planted test that exercises the same scanner path.
- A deny-list of modules leaks transitive imports; an explicit allow-list does not.

## Open

- Dynamic imports through `importlib.import_module` or `__import__` are not visible to the AST import scanner.
- The import-time check of what `import sharpit.cli` loads belongs to the entry-point task.
- Safety-model wording for the CLI HTTP client belongs to the documentation task.
