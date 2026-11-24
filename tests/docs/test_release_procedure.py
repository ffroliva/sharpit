"""Release commands preserve staging ancestry and bind approval to the scanned draft."""

import os
import re
import shutil
import subprocess
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
        (9, r'gh pr merge "\$N" --merge --match-head-commit "\$\{VERIFIED_SHA:\?\}"'),
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


@pytest.mark.parametrize(
    "name",
    [
        "src/sharpit/__init__.py",
        "plugins/sharpit/plugin.json",
        "plugins/sharpit/.claude-plugin/plugin.json",
        "tests/test_packaging.py",
        "CHANGELOG.md",
    ],
)
def test_release_files_staged(name):
    assert name in next(line.split() for line in step(7).splitlines() if line.startswith("git add "))


def test_windows_cleanup_recovery():
    assert "held `.venv`" in step(9)
    assert "manual" in step(9)


@pytest.fixture
def bash():
    executable = shutil.which("bash")
    if os.name == "nt" and (git := shutil.which("git")):
        bundled = Path(git).resolve().parents[1] / "bin" / "bash.exe"
        if bundled.is_file():
            executable = str(bundled)
    if not executable:
        pytest.skip("Bash is unavailable")
    return executable


def run_blocks(bash, number, failure):
    blocks = re.findall(r"```bash\n(.*?)\n```", step(number), re.DOTALL)
    markers = ("STAGING_PR=",) if number != 9 else ('gh pr checks "$N"', 'gh pr merge "$N"', "git push origin --delete")
    commands = "\n".join(block for block in blocks if any(marker in block for marker in markers))
    assert "gh pr merge" in commands
    stubs = r"""
N=9; version=1; stage=stage; VERIFIED_SHA=head; VERIFIED_BASE=base; main_checkout=.
gh() {
    echo "gh $*" >&2
    case "$1 $2" in
        "pr create") echo staging; [ "$failure" != create ];;
        "pr checks") [ "$failure" != checks ];;
        "pr view") case "$*" in
            *headRefOid*) [ "$failure" = head ] && echo changed || echo head;;
            *) [ "$failure" = branch ] && echo changed || echo main;;
        esac;;
        "pr merge") [ "$failure" != merge ];;
        *) [ "$failure" = base ] && echo changed || echo base;;
    esac
}
git() { echo "git $*" >&2; case "$1" in rev-parse) echo head;; push) [ "$failure" != delete ];; esac; }
uv() { echo "uv $*" >&2; }
[ "$failure" = unset ] && unset VERIFIED_SHA
"""
    result = subprocess.run(
        [bash, "-c", stubs + "\n" + commands],
        env={**os.environ, "failure": failure},
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    return result.stderr


@pytest.mark.parametrize(
    ("number", "failure"),
    [
        (7, "create"),
        (7, "checks"),
        (8, "create"),
        (8, "checks"),
        (9, "checks"),
        (9, "head"),
        (9, "branch"),
        (9, "base"),
        (9, "unset"),
    ],
)
def test_failed_guard_blocks_merge(bash, number, failure):
    trace = run_blocks(bash, number, failure)
    assert "gh pr merge" not in trace
    assert "git push origin --delete" not in trace


@pytest.mark.parametrize("number", [7, 8, 9])
def test_checked_commit_is_merged(bash, number):
    assert "--match-head-commit head" in run_blocks(bash, number, "")


def test_failed_merge_blocks_cleanup(bash):
    trace = run_blocks(bash, 9, "merge")
    assert "git push origin --delete" not in trace
    assert "git worktree remove" not in trace


def test_cleanup_independent(bash):
    trace = run_blocks(bash, 9, "delete")
    assert "git push origin --delete" in trace
    assert "git worktree remove" in trace
