## Summary

<!-- Concise summary of the changes in this pull request. -->

## Linked Issue

<!-- Link to an existing issue, or describe the problem addressed. -->
Closes #

## Four Gates Checklist

All four gates must pass before requesting review:

- [ ] `uv run ruff check`
- [ ] `uv run ruff format --check`
- [ ] `uv run pyright`
- [ ] `uv run pytest -q -n auto`

## Test-Driven Development (Finding -> Test -> Red)

<!-- Note the regression or requirement test that failed red on an assertion before implementation:
     finding -> test -> red output -->

| Finding / Requirement | Test Node ID | Red Assertion Output |
|---|---|---|
| | | |

## Contribution Checklist

- [ ] Every non-merge commit carries `Signed-off-by: Name <email>` matching the commit author (`git commit -s`).
- [ ] No AI attribution: no model attribution trailers, co-author trailers, or machine generation lines in commits or the PR description.
- [ ] Changes adhere to the repository working rules in `AGENTS.md`.
- [ ] Each new `NOSONAR` is listed below with the refactor that was tried and why it was rejected (`AGENTS.md`, architecture rule 7), or there is none.
