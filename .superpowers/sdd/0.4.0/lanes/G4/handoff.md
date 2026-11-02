# Lane G4 handoff

Implementer: antigravity-0-4-0-g4
Lane plan: `docs/superpowers/plans/2026-11-01-sharpit-0.4.0/G4-hygiene.md`
Branch / worktree: `lane/0.4.0-G4` in `C:\development\github\sharpit-wt\0.4.0-G4`

## Status

- Done:
  - Task 1: Establish documentation assertions from repository facts (`0aacb9134c8bf1a91d9e2df66dbee287470c501d`)
  - Task 2: Refresh README for adoption (`fb91ef991a5a07509806f7442fccfdcdcc5dbd6f`)
  - Task 3: Add SECURITY.md with supported-version and reporting policy (red `46a3c9a5a78c5c7cc32f4a96c1a754b38e718c40`, fix `129304c06212cc384d8de7c2a3ec17070ac2b285`)
  - Task 4: Add Dependabot coverage and fix stale skill index (red `d965c101464d448563da5f61d08e789ddb25b871`, fix `141140cf947753abe45fe10a690fbc919fe3deca`)
  - Task 5: Review claims and record evidence
- Next step: coordinator runs `lane_gate.py` and merges G4 into `release/0.4.0`
- Last green command: `uv run pytest -q -n 4` -> 3574 passed, 5 skipped in 240.27s (log: `..\0.4.0-integration\.superpowers\sdd\0.4.0\logs\G4-pytest.log`)
- Open findings: none

## How to resume

Worktree `C:\development\github\sharpit-wt\0.4.0-G4`, branch `lane/0.4.0-G4`.
All tasks 1–5 are complete and all four gates pass cleanly.

## Decisions

- **README.md adoption lead**: Replaced stale "sharpit is not on PyPI yet" git installation with published package name and documented extra `pip install "sharpit[fastapi]"` matching `pyproject.toml` and current version `0.3.0` from `sharpit.__version__`. Positioned the CI gate (`pytest --sharpit`) and gflow-cli outside proof (5,662 tests, 0 unattributed SQL statements, 6 N+1 query defects caught) before the 60-seconds quickstart and architecture details (§5.4).
- **SECURITY.md private route and egress boundary**: Added supported versions table (0.3.x / 0.3.0 supported) and directed vulnerability reports to private GitHub Security Advisories (`https://github.com/ffroliva/sharpit/security/advisories/new`) without public issue routing. Explicitly documented the network egress boundary: only OSV (`src/sharpit/engine/collectors/vulns/osv.py`) and EPSS (`src/sharpit/engine/collectors/vulns/epss.py`) gatekeepers make network requests; all ordinary GET routes and MCP tools are strictly local (§5.4, G4 Task 3).
- **.github/dependabot.yml**: Configured updates for `pip` at `/`, `github-actions` at `/`, and `npm` at `/ui` with weekly intervals and `chore(deps)` commit message prefix (§5.4, G4 Task 4).
- **skills/README.md**: Updated line 22 from stale "Labelled pre-release." to "How to install, configure and use sharpit in a FastAPI app.", preserving the user-facing skill entry without modifying unrelated content (§5.4, G4 Task 4).

## Red tests

| Test id | Red SHA | Assertion message |
|---|---|---|
| `tests/docs/test_procurement_docs.py::test_readme_install_uses_current_pypi_version_and_valid_extra` | `0aacb9134c8bf1a91d9e2df66dbee287470c501d` | `assert 'not on PyPI yet' not in readme_text` |
| `tests/docs/test_procurement_docs.py::test_readme_gate_and_gflow_proof_precede_details` | `0aacb9134c8bf1a91d9e2df66dbee287470c501d` | `assert proof_match is not None` |
| `tests/docs/test_procurement_docs.py::test_security_policy_names_supported_versions` | `46a3c9a5a78c5c7cc32f4a96c1a754b38e718c40` | `assert security_path.is_file()` |
| `tests/docs/test_procurement_docs.py::test_security_policy_has_private_reporting_route` | `46a3c9a5a78c5c7cc32f4a96c1a754b38e718c40` | `assert security_path.is_file()` |
| `tests/docs/test_procurement_docs.py::test_security_policy_network_claim_matches_gatekeepers` | `46a3c9a5a78c5c7cc32f4a96c1a754b38e718c40` | `assert security_path.is_file()` |
| `tests/docs/test_procurement_docs.py::test_dependabot_covers_uv_pip_actions_and_ui_npm` | `d965c101464d448563da5f61d08e789ddb25b871` | `assert dependabot_path.is_file()` |
| `tests/docs/test_procurement_docs.py::test_skills_readme_stale_line_corrected` | `d965c101464d448563da5f61d08e789ddb25b871` | `assert 'Labelled pre-release' not in skills_text` |

## Evidence (C2)

- `findings.md`: table with 7 findings fixed, each with its red SHA, assertion message, and fix commit.
- `field-map.md`: `N/A — not a panel lane`.
- `checklist.md`: spec §6.1 items 1–10 in order with evidence paths.
- Gates log: `C:\development\github\sharpit-wt\0.4.0-integration\.superpowers\sdd\0.4.0\logs\G4-pytest.log`.
