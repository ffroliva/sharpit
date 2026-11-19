# Lane A3: Static Security Analysis Rule SEC-STATIC-001 (BootUI 2.4.0 #1597)

> **For agentic workers:** one task at a time; `/sharpit:check` before every commit; `scripts/dev/red_check.py`
> before every `test:` commit. Read the named BootUI files at `v2.4.0` in a BootUI clone; never from a summary.

**Goal:** port BootUI 2.4.0's `SEC-STATIC-001` static security analyzer detection rule to sharpit, inspecting
bounded local build files and configuration without executing analyzers or claiming runtime security evidence.

**Production paths:**
- `src/sharpit/engine/appsource.py:find_pyproject_path`
- `src/sharpit/engine/collectors/architecture/contracts.py:read_contracts`
- `src/sharpit/engine/collectors/security/static_analysis.py:StaticSecurityAnalysisDetector.inspect`
- `src/sharpit/engine/collectors/security/report.py:scan_evaluation`

## Scenarios

| Scenario | Expected behaviour |
|---|---|
| Project root has no readable build file | `State.NOT_APPLICABLE`; silent on security scan |
| Project root has `pyproject.toml` without security analyzers | `State.NOT_CONFIGURED`; emits `SEC-STATIC-001` INFO finding |
| Project root declares Bandit in `pyproject.toml`, `setup.cfg`, `tox.ini`, or `requirements*.txt` | `State.CONFIGURED`; no violation, rule evaluated |
| Project root declares Semgrep config (`.semgrep.yml`, etc.) or in workflows/requirements | `State.CONFIGURED`; no violation, rule evaluated |
| Project root has a `sonar-project.properties` file or workflow scanner | `State.CONFIGURED`; no violation, rule evaluated |
| Project has CodeQL action workflow in `.github/workflows` | `State.CONFIGURED`; no violation, rule evaluated |
| Ruff configured with `select = ["S"]` | `State.CONFIGURED`; security rules selected |
| Ruff configured with `select = ["ALL"]` and `ignore = ["S"]` | `State.NOT_CONFIGURED`; S rules excluded |
| Ruff with external `ruff.toml` or `extend = ...` | `State.INDETERMINATE`; external/delegated configuration cannot be bounded |
| Build file exceeds 1 MiB or is malformed | `State.INDETERMINATE`; safe failure with fixed limitation text |
| Build file is a symlink, junction, or FIFO | Refused safely without blocking or following; `State.INDETERMINATE` |
| More than 64 workflow files | `State.INDETERMINATE`; bounded directory inspection |
| Non-FastAPI host with readable build file | `PARTIAL` scan with `SEC-STATIC-001` evaluated and 0 filter chains |
| GET `/security`, MCP or CLI tool read | Zero files opened; reads have no side effects |
| Any parse or inspection failure | Fixed text only; secret canaries in build files are never leaked |

## Tasks

- [x] **Step 1:** Move `find_pyproject_path` from `engine/collectors/architecture/contracts.py` to `src/sharpit/engine/appsource.py` with site-packages guard; architecture collector re-exports or reuses from `appsource`.
- [x] **Step 2:** Create `src/sharpit/engine/collectors/security/static_analysis.py` with bounded file reading, symlink/junction/FIFO safety, YAML comment stripping, Python analyzer detection (Bandit, Semgrep, a `sonar-project.properties` file, CodeQL, Ruff), and `StaticSecurityAnalysisRule`.
- [x] **Step 3:** Wire `StaticSecurityAnalysisDetector` into `src/sharpit/engine/collectors/security/report.py` (`scan_evaluation` and `SecurityService`).
- [x] **Step 4:** Port the 22 `StaticSecurityAnalysisDetectorTests` cases adapted to Python project structure.
- [x] **Step 5:** Write safety, secrecy, performance, boundary, and non-FastAPI test suite covering all 9 required verification points.
- [x] **Step 6:** Update `docs/security-advisor-checks.md`, CHANGELOG, and `docs/reference/matrix-updates/a3-sec-static.tsv`. Run all verification gates.
- [x] **Fix Round 1:** Address review findings: PEP 508 variants, PEP 735 dependency groups, build tool dev-deps, pre-commit quoted/local hooks, monorepo candidates, runner commands, bandit-action, ruff.toml independence, os.O_BINARY Windows 0x1A safety, not-present model limitations preservation, static-only analyzer/disclaimer texts, rule description Python limits, watch_sources read safety positive control, build_inputs project_root resolution, shared TOML coercion in appsource, _split_shell_commands index loop, dist-packages refusal.
