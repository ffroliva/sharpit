# 0.7.0 review fixes

| Scenario | Expected behaviour |
|---|---|
| Subproject and repository have Ruff config | The project-local closest config determines analyzer detection |
| `uv run` or `uvx` receives `--isolated` | The following analyzer command is detected |
| Bounded file inspection encounters unsafe or unreadable inputs | Existing indeterminate behavior and byte limits remain unchanged |
| Capture outcome/template helpers run | Their own error handling remains the sole protection |
| A partial assessment is summarized in CLI, session, and report output | Shared semantics and existing output remain byte-identical |
| PostgreSQL relation completeness has no producer | No unobservable diagnostic is synthesized |
| UI package and capture fixture scripts are used | No dead exports; both old script entry points remain usable |

- [ ] **Step 1:** Add Ruff precedence and runner-option regressions; observe red with `red_check.py`.
- [ ] **Step 2:** Fix the two static-analysis bugs.
- [ ] **Step 3:** Apply requested lean refactors and remove unobservable/dead code.
- [ ] **Step 4:** Run lane and common gates, then commit the complete fix.

Production paths: `engine/collectors/security/static_analysis.py` (analyzer detection), `engine/fastapi/capture.py` (request outcome), `engine/testsession/outcome.py` and `report/summary.py` (partial notes), `engine/collectors/database_advisor/report.py` (diagnostics), UI load errors, and `scripts/capture_bootui.py` (fixture capture).
