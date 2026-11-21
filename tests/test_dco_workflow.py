"""The DCO contribution check: a pull_request_target workflow that treats the pull request as data only.

`pull_request_target` runs with the base repository's token, so the workflow must never check out or run code from the
pull request. The file is read as text, line by line; it stays small and flat so each check is exact.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "dco.yml"
TEXT = PATH.read_text(encoding="utf-8")
LINES = TEXT.splitlines()
PIN = re.compile(r"@[0-9a-f]{40}( |$)")
PIN_COMMENT = re.compile(r" # v\d+\.\d+\.\d+$")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _block(header: str) -> list[str]:
    """The lines nested under the top-level key `header:`, without the header."""
    start = next(i for i, line in enumerate(LINES) if line.startswith(header + ":"))
    block: list[str] = []
    for line in LINES[start + 1 :]:
        if line.strip() and _indent(line) == 0:
            break
        block.append(line)
    return block


def _uses() -> list[str]:
    """The value of every `uses:` line."""
    return [line.split("uses:", 1)[1].strip() for line in LINES if re.match(r"\s*(- )?uses:", line)]


def _job_permissions() -> list[str]:
    """Every grant under a nested `permissions:` key (the top-level key is checked on its own)."""
    grants: list[str] = []
    for i, line in enumerate(LINES):
        if _indent(line) == 0 or not line.strip().startswith("permissions:"):
            continue
        inline = line.split(":", 1)[1].strip()
        if inline:
            grants.append(inline)
        for nested in LINES[i + 1 :]:
            if not nested.strip() or _indent(nested) <= _indent(line):
                break
            grants.append(nested.strip())
    return grants


def _run_values() -> list[str]:
    """The text of every `run:` step, inline or as a block scalar."""
    values: list[str] = []
    for i, line in enumerate(LINES):
        match = re.match(r"(\s*)(- )?run:(.*)$", line)
        if not match:
            continue
        indent = len(match.group(1)) + (2 if match.group(2) else 0)
        value = [match.group(3)]
        for nested in LINES[i + 1 :]:
            if nested.strip() and _indent(nested) <= indent:
                break
            value.append(nested)
        values.append("\n".join(value))
    return values


def test_the_trigger_is_exactly_pull_request_target() -> None:
    triggers = [line.strip() for line in _block("on") if _indent(line) == 2]
    assert triggers == ["pull_request_target:"]


def test_the_trigger_types_are_the_four_that_move_a_sign_off() -> None:
    types = [line.strip() for line in _block("on") if line.strip().startswith("types:")]
    assert types == ["types: [opened, synchronize, reopened, edited]"]


def test_top_level_permissions_are_empty() -> None:
    assert "permissions: {}" in LINES


def test_no_job_grants_more_than_read_on_contents_and_pull_requests() -> None:
    assert sorted(_job_permissions()) == ["contents: read", "pull-requests: read"]


def test_no_step_checks_out_a_ref() -> None:
    refs = [line.strip() for line in LINES if re.match(r"\s*ref:", line)]
    assert refs == []


@pytest.mark.parametrize("head", ["pull_request.head", "head.sha", "head.ref"])
def test_the_workflow_never_names_the_pull_request_head(head: str) -> None:
    assert head not in TEXT


def test_the_checkout_does_not_persist_credentials() -> None:
    assert any(line.strip() == "persist-credentials: false" for line in LINES)


def test_every_action_is_pinned_by_a_full_commit() -> None:
    unpinned = [use for use in _uses() if not PIN.search(use)]
    assert unpinned == []


def test_every_pinned_action_names_its_release() -> None:
    uncommented = [use for use in _uses() if not PIN_COMMENT.search(" " + use)]
    assert uncommented == []


def test_no_run_value_interpolates_an_expression() -> None:
    interpolated = [value for value in _run_values() if "${{" in value]
    assert interpolated == []


def test_a_step_runs_the_check_script() -> None:
    assert any("scripts/ci/dco_check.py" in value for value in _run_values())
