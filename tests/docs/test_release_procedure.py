"""Release commands preserve staging ancestry and bind approval to the scanned draft."""

import re
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[2] / "skills/release/SKILL.md"


def step(number):
    return SKILL.read_text(encoding="utf-8").split(f"**{number}. ", 1)[1].split(f"**{number + 1}. ", 1)[0]


@pytest.mark.parametrize(
    ("number", "pattern"),
    [
        (3, r"origin/main"),
        (3, r"origin/release/\$version"),
        (7, r'gh pr merge "\$STAGING_PR" --merge'),
        (8, r'gh pr merge "\$STAGING_PR" --merge'),
        (8, r"git merge .*origin/main"),
        (8, r"gh pr create .*--draft .*--base main .*--head \"chore/release-\$version\""),
        (8, r"gh pr create .*--draft .*--base main .*--head \"release/\$version\""),
        (8, r"uv run python scripts/ci/ship_scan.py "),
        (9, r"/sharpit:llm-council --tier high"),
        (9, r"gh api repos/ffroliva/sharpit/git/ref/heads/main --jq .object.sha"),
        (9, r'gh pr ready "\$N" --undo'),
        (9, r'gh pr merge "\$N" --merge --match-head-commit "\$VERIFIED_SHA"'),
    ],
)
def test_release_step(number, pattern):
    assert re.search(pattern, step(number)), pattern


def test_ready_after_review_and_scan():
    assert not re.search(r"^gh pr ready .*?(?<! --undo)$", step(8), re.MULTILINE)
    actions = re.findall(
        r'/sharpit:llm-council --tier high|scripts/ci/ship_scan.py|^gh pr ready "\$N"$', step(9), re.MULTILINE
    )
    assert actions == ["/sharpit:llm-council --tier high", "scripts/ci/ship_scan.py", 'gh pr ready "$N"']


def test_explicit_chore_cleanup():
    assert "--delete-branch" not in step(9)
    assert 'git push origin --delete "chore/release-$version"' in step(9)
