# Contributing to sharpit

sharpit is an embedded, local-only developer console for Python web applications, porting the functionality of BootUI (Spring Boot) to Python and FastAPI.

The repository's working rules are documented in [AGENTS.md](AGENTS.md); this guide summarizes the development workflow, quality gates, and contribution requirements for contributors.

## Licensing and Developer Certificate of Origin

sharpit is licensed under the Apache License, Version 2.0 (see [LICENSE](LICENSE)), and Section 5 of Apache-2.0 governs all contributions submitted to the project.

Every non-merge commit carries a Developer Certificate of Origin (DCO) sign-off line matching the commit author:
```text
Signed-off-by: Author Name <author.email@example.com>
```
Contributors add this sign-off automatically to each commit by using `git commit -s`:
```bash
git commit -s -m "feat: description of change"
```
The Developer Certificate of Origin 1.1 text is available at <https://developercertificate.org>. A pull request check workflow enforces the sign-off requirement on all pull requests; Dependabot commits are exempt.

To repair a missing sign-off on a local branch:
```bash
git rebase --signoff <base-branch>
git push --force-with-lease
```

When a commit that is already pushed or merged cannot be rewritten, its author adds a remediation commit to the same pull request instead. The commit is signed off like any other and carries one line per remediated commit, written by the author of that commit:
```text
I, Author Name <author.email@example.com>, hereby add my Signed-off-by to this commit: <sha>
```
The sign-off check accepts a commit whose author, name and email, matches the remediation line of a signed commit of that author in the same pull request. The `<sha>` is the full or an abbreviated (at least 7 characters) commit hash.

## Setup

Environment setup and dependency management use [uv](https://github.com/astral-sh/uv):

```bash
uv sync --extra test
```

## The Four Quality Gates

Before submitting a pull request, all four quality gates must pass locally:

1. **Linting**:
   ```bash
   uv run ruff check
   ```
2. **Formatting**:
   ```bash
   uv run ruff format --check
   ```
   Ruff also formats Python code blocks in Markdown documentation files.
3. **Type Checking**:
   ```bash
   uv run pyright
   ```
4. **Test Suite**:
   ```bash
   uv run pytest -q -n auto
   ```
   Tests run in parallel using `pytest-xdist`.

## Red-First Tests and Test-Driven Development

All bug fixes and additions follow test-driven development:

1. **Assertion-first failure**: The test fails on an assertion specifically naming the defect or behavior under test, never on an `ImportError`, `AttributeError`, or collection crash.
2. **One condition per assert**: Each assertion tests a single condition (following ruff `PT018`) so failures identify the exact issue.
3. **Verification with `scripts/dev/red_check.py`**:
   Run the red check script before committing a test:
   ```bash
   uv run python scripts/dev/red_check.py tests/path/to/test_file.py::test_name
   ```
   The check requires an assertion failure located under `tests/`.
4. **Implementation**: The implementation makes the red test pass without regressing existing tests.

For detailed guidelines on writing test assertions, see the "Writing tests that prove something" section of [AGENTS.md](AGENTS.md).

## Port BootUI, Do Not Reinvent

sharpit ports BootUI functionality rather than inventing independent designs:

- Contributors read the BootUI source code at the pinned release tag before writing code.
- Ported tests cite their BootUI counterpart:
  ```python
  # ported: LocalhostGuardTests.rejectsMalformedHost
  ```
- Any adaptations required by Python, FastAPI, or SQLAlchemy are documented as deviation entries.
- The development sequence and workflow are documented in [docs/development/workflow.md](docs/development/workflow.md).

## Commits and Pull Requests

- **Commit messages**: Use conventional commit prefixes (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`) with concise descriptions.
- **Explicit staging**: Stage files with explicit paths using `git add <path>` rather than staging entire trees.
- **No AI attribution**: Commits and pull request descriptions must not contain machine or model attribution trailers or "Generated with" lines.
- **Pull requests**: Fill out `.github/PULL_REQUEST_TEMPLATE.md`, verify that the four gates pass, and link related issues.
