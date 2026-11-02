# Lane G4 findings

## Red tests (test unchanged since its red commit)

| Finding | Test | Red SHA | Assertion message | Disposition |
|---|---|---|---|---|
| README.md install commands must use published PyPI package and valid extras instead of stale git clone | `tests/docs/test_procurement_docs.py::test_readme_install_uses_current_pypi_version_and_valid_extra` | `0aacb9134c8bf1a91d9e2df66dbee287470c501d` | `assert 'not on PyPI yet' not in readme_text` | Fixed in `fb91ef991a5a07509806f7442fccfdcdcc5dbd6f` |
| Round 1 finding 2: SECURITY.md supported versions (verifiable PyPI support boundary without exact __version__ duplication, remove 48-hour SLA) | `tests/docs/test_procurement_docs.py::test_security_policy_names_supported_versions` | `15b9c8a4f1701d78ae1b1721387398f6fe9971a9` | `assert "latest release on pypi" in supported_section.lower()` | Fixed in `42271a6c2310dd0a3816229b99fadad9a8b0bdd1` |
| Round 1 finding 5: skills/README.md restore pre-release label meaning, correct SonarCloud CI description, remove CHANGELOG.md from missing files list | `tests/docs/test_procurement_docs.py::test_skills_readme_stale_line_corrected` | `48b6815d73a705071d5b7c2f2e3760e5729d8cb0` | `assert re.search(...) is not None` | Fixed in `7933cc716bb04e10d908035e6a14415e957caa9d` |

## Historical reds (test changed after red commit)

Each test below was first pinned red at an earlier SHA, then changed (formatter or a later fix round). Fixes: README gflow proof `c2954984cbe7c449ff573b91b0db977ecd2febbf` (round 0 `fb91ef991a5a07509806f7442fccfdcdcc5dbd6f`), SECURITY.md reporting route `42271a6c2310dd0a3816229b99fadad9a8b0bdd1` (round 0 `129304c06212cc384d8de7c2a3ec17070ac2b285`), SECURITY.md egress `37a2a08dc2e2c5ecdb64a6ea5eda0419b5ac0648`, dependabot `cbbb2768d394bcc7c5bf1b72b29dc363ad4f9abe` (round 0 `141140cf947753abe45fe10a690fbc919fe3deca`), skills README round 0 `141140cf947753abe45fe10a690fbc919fe3deca`.

| Test id | Historical SHA | Reason |
|---|---|---|
| `tests/docs/test_procurement_docs.py::test_readme_gate_and_gflow_proof_precede_details` | `0aacb9134c8bf1a91d9e2df66dbee287470c501d` | test changed after red commit (formatter / later fix round) |
| `tests/docs/test_procurement_docs.py::test_readme_gate_and_gflow_proof_precede_details` | `3fff0b186f6be5ee812eab218767488c09c2c85c` | test changed after red commit (formatter / later fix round) |
| `tests/docs/test_procurement_docs.py::test_security_policy_names_supported_versions` | `46a3c9a5a78c5c7cc32f4a96c1a754b38e718c40` | test changed after red commit (formatter / later fix round) |
| `tests/docs/test_procurement_docs.py::test_security_policy_has_private_reporting_route` | `46a3c9a5a78c5c7cc32f4a96c1a754b38e718c40` | test changed after red commit (formatter / later fix round) |
| `tests/docs/test_procurement_docs.py::test_security_policy_has_private_reporting_route` | `15b9c8a4f1701d78ae1b1721387398f6fe9971a9` | test changed after red commit (formatter / later fix round) |
| `tests/docs/test_procurement_docs.py::test_security_policy_network_claim_matches_gatekeepers` | `46a3c9a5a78c5c7cc32f4a96c1a754b38e718c40` | test changed after red commit (formatter / later fix round) |
| `tests/docs/test_procurement_docs.py::test_security_policy_network_claim_matches_gatekeepers` | `6afba7b2d067f808cf3c09bc52c1c38a37aa0530` | test changed after red commit (formatter / later fix round) |
| `tests/docs/test_procurement_docs.py::test_dependabot_covers_uv_pip_actions_and_ui_npm` | `d965c101464d448563da5f61d08e789ddb25b871` | test changed after red commit (formatter / later fix round) |
| `tests/docs/test_procurement_docs.py::test_dependabot_covers_uv_pip_actions_and_ui_npm` | `08f931c2b3e725a7fc1fc4fe34aa1fb2551c0dcf` | test changed after red commit (formatter / later fix round) |
| `tests/docs/test_procurement_docs.py::test_skills_readme_stale_line_corrected` | `d965c101464d448563da5f61d08e789ddb25b871` | test changed after red commit (formatter / later fix round) |
