# Lane G4 handoff

Implementer: antigravity-0-4-0-g4
Lane plan: `docs/superpowers/plans/2026-11-01-sharpit-0.4.0/G4-hygiene.md`
Branch / worktree: `lane/0.4.0-G4` in `C:\development\github\sharpit-wt\0.4.0-G4`

## Status

- State: DONE
- Tasks completed:
  - Round 0:
    - Task 1: Establish documentation assertions from repository facts (`0aacb9134c8bf1a91d9e2df66dbee287470c501d`)
    - Task 2: Refresh README for adoption (`fb91ef991a5a07509806f7442fccfdcdcc5dbd6f`)
    - Task 3: Add SECURITY.md with supported-version and reporting policy (red `46a3c9a5a78c5c7cc32f4a96c1a754b38e718c40`, fix `129304c06212cc384d8de7c2a3ec17070ac2b285`)
    - Task 4: Add Dependabot coverage and fix stale skill index (red `d965c101464d448563da5f61d08e789ddb25b871`, fix `141140cf947753abe45fe10a690fbc919fe3deca`)
    - Task 5: Review claims and record evidence
  - Round 1 fixes:
    - Finding 1: README gflow-cli proof accuracy (red `3fff0b186f6be5ee812eab218767488c09c2c85c`, fix `c2954984cbe7c449ff573b91b0db977ecd2febbf`)
    - Finding 2: SECURITY.md reporting route & support boundary (red `15b9c8a4f1701d78ae1b1721387398f6fe9971a9`, fix `42271a6c2310dd0a3816229b99fadad9a8b0bdd1`)
    - Finding 3: SECURITY.md egress accuracy & local boundaries (red `6afba7b2d067f808cf3c09bc52c1c38a37aa0530`, fix `37a2a08dc2e2c5ecdb64a6ea5eda0419b5ac0648`)
    - Finding 4: .github/dependabot.yml uv at /, pip at /website, npm at /ui grouped with limit 2 & drift comment; structural YAML parse in test (red `08f931c2b3e725a7fc1fc4fe34aa1fb2551c0dcf`, fix `cbbb2768d394bcc7c5bf1b72b29dc363ad4f9abe`)
    - Finding 5: skills/README.md pre-release label, SonarCloud in CI, CHANGELOG existence (red `48b6815d73a705071d5b7c2f2e3760e5729d8cb0`, fix `7933cc716bb04e10d908035e6a14415e957caa9d`)
    - Test suite simplification & formatting: `47d3dbb4d06c59d9c5b2cb612df59556ceba4840`
- Next step: coordinator runs `lane_gate.py` and merges G4 into `release/0.4.0`
- Last green command: `uv run pytest -q -n 4` -> (logged to `..\0.4.0-integration\.superpowers\sdd\0.4.0\logs\G4-pytest.log`)
- Open findings: none

## Decisions

- **README.md gflow-cli proof**: Dropped "independent" claim; explicitly stated that tests were run by sharpit's author on the 0.3.0 integration branch; linked using "sharpit's own report"; accurately stated ~53k statements executed (27,997 attributed + 25,092 filtered, 0 unattributed) and 6 N+1 findings (1 real defect, 2 noise filtered since 0.3.0, 3 expected polling), noting 5 tests failed by sharpit gates.
- **SECURITY.md reporting route & support boundary**: Documented that GitHub private vulnerability reporting is currently disabled; instructed reporters to open an issue titled "Security contact request" containing no details until enabled; removed unsupported 48-hour SLA; defined verifiable support boundary (latest release on PyPI, 0.3.x) without hardcoding exact `__version__`.
- **SECURITY.md network egress & local boundaries**: Dropped "entirely offline" claim; accurately documented that GET routes and MCP tools open no sockets; health check (POST) pings configured DB engines and runs user health callables; database panels run read-only SQL; explicit vulnerability scan (POST) sends up to 500 package names/versions to OSV and CVE IDs to EPSS; documented configuration/disable env vars `SHARPIT_VULNERABILITIES_OSV_BASE_URI`, `SHARPIT_VULNERABILITIES_EPSS_BASE_URI`, `SHARPIT_VULNERABILITIES_OSV_ENABLED=false`, `SHARPIT_VULNERABILITIES_EPSS_ENABLED=false`.
- **.github/dependabot.yml**: Switched root ecosystem from pip to uv; added pip for `/website` (requirements.txt); configured npm at `/ui` grouped into one weekly PR with `open-pull-requests-limit: 2` and documented that PRs require committing `npm --prefix ui run build` assets to pass CI drift check. Added structural YAML parser in `test_procurement_docs.py` replacing regexes.
- **skills/README.md**: Restored pre-release label meaning in skill index line 22; corrected line 54 to cite SonarCloud CI ratchet rather than claiming no project; corrected line 57 to cite only `KNOWN_ISSUES.md` as missing.
- **Out-of-scope references**: Listed stale "not on PyPI" lines in `website/docs/installation.md:3` and `skills/sharpit/SKILL.md:25` in `.superpowers/sdd/0.4.0/lanes/G4/docs.md` for final integration step.

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
| `tests/docs/test_procurement_docs.py::test_readme_gate_and_gflow_proof_precede_details` | `3fff0b186f6be5ee812eab218767488c09c2c85c` | `assert "independent" not in proof_section.lower()` |
| `tests/docs/test_procurement_docs.py::test_security_policy_names_supported_versions` & `tests/docs/test_procurement_docs.py::test_security_policy_has_private_reporting_route` | `15b9c8a4f1701d78ae1b1721387398f6fe9971a9` | `assert "latest release on pypi" in supported_section.lower()` & `assert "Report a vulnerability" in reporting_section` |
| `tests/docs/test_procurement_docs.py::test_security_policy_network_claim_matches_gatekeepers` | `6afba7b2d067f808cf3c09bc52c1c38a37aa0530` | `assert "entirely offline" not in section.lower()` |
| `tests/docs/test_procurement_docs.py::test_dependabot_covers_uv_pip_actions_and_ui_npm` | `08f931c2b3e725a7fc1fc4fe34aa1fb2551c0dcf` | `assert len(updates) >= 4` |
| `tests/docs/test_procurement_docs.py::test_skills_readme_stale_line_corrected` | `48b6815d73a705071d5b7c2f2e3760e5729d8cb0` | `assert re.search(...) is not None` |

## Evidence (C2)

- `findings.md`: table with round 0 and round 1 findings fixed, each with its red SHA, assertion message, and fix commit.
- `field-map.md`: `N/A — not a panel lane`.
- `checklist.md`: spec §6.1 items 1–10 in order with evidence paths.
- `docs.md`: out-of-scope "not on PyPI" references deferred to final integration.
- Gates log: `C:\development\github\sharpit-wt\0.4.0-integration\.superpowers\sdd\0.4.0\logs\G4-pytest.log`.
