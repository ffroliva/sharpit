# G4 — Procurement Hygiene Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans. One atomic task/commit at a time; begin after F is merged.

**Goal:** Make sharpit’s adoption and security posture clear to evaluators through accurate installation and CI guidance, a private vulnerability-reporting policy, and dependency update automation.

**Architecture:** Documentation and repository automation only. Keep claims tied to current package metadata, CI workflow, dependency configuration, and §5.4; do not modify product runtime behavior.

**Tech Stack:** Markdown, GitHub Dependabot YAML, repository CI/config inspection; no code or dependency changes.

**Spec:** `docs/superpowers/specs/2026-11-01-sharpit-0.4.0-design.md` §5.4 and §13.

## Header and ownership

- **Lane:** G4.
- **Worker profile:** S/M, mechanical with judgement-heavy security wording.
- **Dependencies:** F (exactly as PLAN.md). G1G2/G3 are not dependencies; verify described flags/action against merged artifacts or describe only accepted spec surface.
- **May touch:** `README.md`, `SECURITY.md` (create if absent), `.github/dependabot.yml`, only the stale line in `skills/README.md`, and this lane’s evidence folder.
- **Must not touch:** Python source, tests, `pyproject.toml`, `uv.lock`, workflows/action code, panel docs owned by feature lanes, `scripts/dev/lane_gate.py`, complexity/sonar baselines, or other README/skill content.

## Global constraints

- State installation from PyPI and current released version accurately; verify against package metadata.
- Lead README with CI gate, gflow-cli proof, and concise “60 seconds” path (§5.4).
- SECURITY policy states supported versions, private reporting route, and that only OSV and EPSS clients make network requests.
- Dependabot covers uv/pip, GitHub Actions, and `ui/` npm using repository conventions.
- Do not claim a panel/action/release shipped unless its lane merged and evidence exists.

## Review Focus

1. README advertises unreleased or unsupported install commands: `test_readme_install_uses_current_pypi_version_and_valid_extra` checks metadata and documented commands.
2. Egress claim mismatches code: `test_security_policy_network_claim_matches_gatekeepers` checks OSV/EPSS gatekeeper modules.
3. Security reporting path is public or ambiguous: `test_security_policy_has_private_reporting_route` requires private instructions without inventing a public issue route.
4. Dependabot misses ecosystem or path: `test_dependabot_covers_uv_pip_actions_and_ui_npm` parses YAML and asserts pip `/`, github-actions `/`, npm `/ui`.
5. README lacks adoption order: `test_readme_gate_and_gflow_proof_precede_details` checks gate/gflow proof precedes the 60-seconds and detail sections.

---

### Task 1: Establish documentation assertions from repository facts

**Files:** Create `tests/docs/test_procurement_docs.py` (documentation-only checks).

**Interfaces:** Tests read current repository metadata/config as source of truth. Check required claims and section ordering, not prose wording except exact commands and network egress names.

- [ ] **Step 1: Failing tests.** Add all five Review Focus tests; expected failures identify missing/stale content.
- [ ] **Step 2: Run targeted docs tests; expected assertion failures only.**
- [ ] **Step 3: Commit** `test: pin procurement documentation requirements`.

### Task 2: Refresh README for adoption

**Files:** Modify `README.md` only.

**Interfaces:** README starts with CI gate and gflow-cli proof, then a `60 seconds` section with correct PyPI install and minimal use; accurately covers current invocation/report outputs and links detailed docs without claiming unmerged work.

- [ ] **Step 1: Failing tests.** `test_readme_install_uses_current_pypi_version_and_valid_extra`, `test_readme_gate_and_gflow_proof_precede_details`.
- [ ] **Step 2: Confirm assertions fail on current README.**
- [ ] **Step 3: Rewrite adoption opening and 60-seconds section from current `pyproject.toml`, CI and proof evidence.**
- [ ] **Step 4: Run README tests; expected PASS.**
- [ ] **Step 5: Commit** `docs: lead README with sharpit CI adoption path`.

### Task 3: Add SECURITY.md with supported-version and reporting policy

**Files:** Create `SECURITY.md`; extend `tests/docs/test_procurement_docs.py`.

**Interfaces:** State supported release/version policy, private vulnerability reporting instructions, response expectations already supported by project policy, and exact egress boundary: OSV and EPSS clients only (`src/sharpit/engine/collectors/vulns/osv.py`, `epss.py`). Do not imply ordinary GET/MCP paths use the network.

- [ ] **Step 1: Failing tests.** Review Focus 2–3; `test_security_policy_names_supported_versions`, `test_security_policy_has_private_reporting_route`, `test_security_policy_network_claim_matches_gatekeepers`.
- [ ] **Step 2: Run tests; expected missing-policy assertions fail.**
- [ ] **Step 3: Write concise policy using the repository’s configured private reporting channel; do not create a new external contact route.**
- [ ] **Step 4: Run tests; expected PASS.**
- [ ] **Step 5: Commit** `docs: add private security reporting policy`.

### Task 4: Add Dependabot coverage and fix stale skill index

**Files:** Create `.github/dependabot.yml`; modify only the stale line in `skills/README.md`; extend `tests/docs/test_procurement_docs.py`.

**Interfaces:** Dependabot updates `pip` at `/`, `github-actions` at `/`, and `npm` at `/ui`; use repository schedule conventions and valid schema. Correct the stale 0.4.0 reference without unrelated edits.

- [ ] **Step 1: Failing tests.** Review Focus 4; `test_dependabot_covers_uv_pip_actions_and_ui_npm`, `test_skills_readme_stale_line_corrected`.
- [ ] **Step 2: Run tests; expected missing/old config assertions fail.**
- [ ] **Step 3: Add three ecosystem entries and update exactly the stale line.**
- [ ] **Step 4: Run YAML/docs assertions; expected PASS.**
- [ ] **Step 5: Commit** `chore: configure dependency update coverage`.

### Task 5: Review claims and record evidence

**Files:** Update only `.superpowers/sdd/0.4.0/lanes/G4/` artifacts.

- [ ] **Step 1:** Check README install against `pyproject.toml`, egress against `osv.py`/`epss.py`, and Dependabot paths against repo folders.
- [ ] **Step 2:** Run targeted docs checks and four standard gates; save output paths pinned to head SHA.
- [ ] **Step 3:** Prepare reviewer findings table and current handoff.
- [ ] **Step 4: Commit** `docs: record procurement hygiene lane evidence`.

### Documentation acceptance checklist

The README stays concise and routes detailed or version-sensitive claims to their canonical documents. Do not duplicate the full panel contract or every option table in the quickstart.

- [ ] **Step 1:** Confirm install command uses the published package name and documented extra only; distinguish installation from running the example.
- [ ] **Step 2:** Confirm the first screen communicates the CI gate and gflow-cli proof before project background or architecture detail.
- [ ] **Step 3:** Confirm the 60-seconds path has one install command, one minimal FastAPI integration, and one command that emits the report.
- [ ] **Step 4:** Confirm no README sentence claims a not-yet-merged action, panel, or version as available.

The security policy must be actionable for a reporter and precise about what sharpit sends externally.

- [ ] **Step 1:** Define supported versions from the repository’s release support policy; if no policy exists, state only the verifiable current support boundary rather than inventing a promise.
- [ ] **Step 2:** Provide private reporting instructions through the repository’s configured security advisory/contact route; do not direct vulnerability details to public issues.
- [ ] **Step 3:** Verify network statement against imports and gatekeeper rules: only OSV and EPSS clients use the network; all other panel reads stay local.
- [ ] **Step 4:** Check Dependabot ecosystem syntax and directory paths against `pyproject.toml`, GitHub workflows, and `ui/package.json`.

## Lane evidence checklist

`.superpowers/sdd/0.4.0/lanes/G4/` contains implementer-owned `handoff.md`, `findings.md`, `field-map.md` (`N/A — not a panel lane`), and `checklist.md`. Checklist follows spec §6.1 items 1–10 in order, mapped to owning tasks with evidence paths or `N/A` plus reason. Coordinator/reviewer alone creates `review.md`, `gate/<name>.log` for ruff-check, ruff-format, pyright, pytest, lowest-direct and no-sqlalchemy, and `live-verify.md` in integration; lane diff cannot touch those paths.

## Definition of done

- [ ] Tasks 1–5 cover every §5.4 deliverable: README (PyPI install, gate/gflow proof, 60 seconds), SECURITY (versions, private reporting, egress), Dependabot’s three ecosystems, stale skills index line.
- [ ] Documentation claims match current repository state and checks pass.
- [ ] Lane evidence passes `scripts/dev/lane_gate.py`; source and dependency files remain untouched.

## Canonical lane conventions (C1–C8)

- Lane id is exactly `G4`; evidence folder is `.superpowers/sdd/0.4.0/lanes/G4/`.
- All lanes consume module names and signatures in F's consumer interface table.
- Golden fixture paths and `tests/golden.py::assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None` follow C3, with no flat panel files.
- A red is a defect-naming assertion, not import/collection failure. No spike test is owned by G4.
- Do not edit shared safety/masking matrices; use `tests/safety/test_g4_safety.py` and `tests/masking/test_g4_masking.py` if needed.
- PLAN.md Review Focus test names remain canonical: `test_readme_install_uses_current_pypi_version_and_valid_extra`, `test_security_policy_network_claim_matches_gatekeepers`, `test_security_policy_has_private_reporting_route`, `test_dependabot_covers_uv_pip_actions_and_ui_npm`, and `test_readme_gate_and_gflow_proof_precede_details`.
- Dependencies are exactly `F`; no G1G2/G3 dependency.
- Checklist follows §6.1 items 1–10 in order; panel-specific items are `N/A — not a panel lane`, with evidence paths for applicable handoff items.

| Spec §6.1 item | G4 task / evidence owner |
|---|---|
| 1 Golden parity | N/A — procurement hygiene lane, not a panel lane. |
| 2 Ported behavior tests | N/A — no BootUI panel behavior is ported. |
| 3 Safety and masking | N/A — no panel data source or new secret source. |
| 4 Gatekeeper | N/A — no library import change. |
| 5 Hot-path overhead | N/A — no hot-path code change. |
| 6 MCP read-only surface | N/A — no MCP surface change. |
| 7 Svelte view | N/A — no panel view. |
| 8 Four gates | Task 5, Step 2: run four gates; coordinator owns gate logs. |
| 9 Live check | N/A — no panel implementation; integration reviewer owns live verification. |
| 10 Handoff | Task 5: current handoff and review findings. |
