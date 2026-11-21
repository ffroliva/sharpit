"""scripts/ci/dco_check.py: every non-merge, non-Dependabot commit carries a Signed-off-by trailer of its author."""

from __future__ import annotations

from typing import Any

from _load import load_script

dco = load_script("scripts/ci/dco_check.py")

MISSING = "missing Signed-off-by"
MISMATCH = "Signed-off-by does not match the commit author"


def _commit(
    message: str,
    *,
    sha: str = "a" * 40,
    name: str = "Ada Lovelace",
    email: str = "ada@example.org",
    login: str | None = "ada",
    parents: int = 1,
) -> dict[str, Any]:
    """One element of the GET /repos/{repo}/pulls/{n}/commits response, reduced to the keys the check reads."""
    return {
        "sha": sha,
        "commit": {"message": message, "author": {"name": name, "email": email}},
        "author": {"login": login} if login else None,
        "parents": [{"sha": str(i) * 40} for i in range(parents)],
    }


def _failures(*commits: dict[str, Any]) -> list[tuple[str, str]]:
    return [(failure.sha, failure.reason) for failure in dco.check_commits(list(commits))]


def test_a_commit_signed_by_its_author_passes() -> None:
    commit = _commit("fix: a thing\n\nSigned-off-by: Ada Lovelace <ada@example.org>\n")
    assert _failures(commit) == []


def test_an_unsigned_commit_fails() -> None:
    commit = _commit("fix: a thing\n\nBody without a trailer.\n")
    assert _failures(commit) == [("a" * 40, MISSING)]


def test_a_sign_off_with_another_email_fails() -> None:
    commit = _commit("fix: a thing\n\nSigned-off-by: Ada Lovelace <someone@example.org>\n")
    assert _failures(commit) == [("a" * 40, MISMATCH)]


def test_a_sign_off_with_another_name_fails() -> None:
    commit = _commit("fix: a thing\n\nSigned-off-by: Grace Hopper <ada@example.org>\n")
    assert _failures(commit) == [("a" * 40, MISMATCH)]


def test_a_sign_off_name_that_differs_only_in_case_fails() -> None:
    commit = _commit("fix: a thing\n\nSigned-off-by: ada lovelace <ada@example.org>\n")
    assert _failures(commit) == [("a" * 40, MISMATCH)]


def test_an_email_that_differs_only_in_case_passes() -> None:
    commit = _commit("fix: a thing\n\nSigned-off-by: Ada Lovelace <ADA@Example.ORG>\n")
    assert _failures(commit) == []


def test_a_merge_commit_is_skipped() -> None:
    merge = _commit("Merge branch 'main'\n\nSigned-off-by: Ada Lovelace <someone@example.org>\n", parents=2)
    assert _failures(merge) == []


def test_a_dependabot_commit_is_skipped() -> None:
    bot = _commit(
        "chore: bump x\n\nSigned-off-by: Dependabot <someone@example.org>\n",
        name="dependabot[bot]",
        email="49699333+dependabot[bot]@users.noreply.github.com",
        login="dependabot[bot]",
    )
    assert _failures(bot) == []


def test_an_author_named_dependabot_without_the_bot_login_is_not_skipped() -> None:
    lookalike = _commit("chore: bump x\n", name="dependabot[bot]", login="not-the-bot")
    assert _failures(lookalike) == [("a" * 40, MISSING)]


def test_a_commit_with_no_linked_account_is_checked() -> None:
    unlinked = _commit("fix: a thing\n", login=None)
    assert _failures(unlinked) == [("a" * 40, MISSING)]


def test_a_sign_off_inside_a_quoted_line_fails() -> None:
    commit = _commit("fix: a thing\n\n> Signed-off-by: Ada Lovelace <ada@example.org>\n")
    assert _failures(commit) == [("a" * 40, MISSING)]


def test_a_sign_off_after_text_on_the_same_line_fails() -> None:
    commit = _commit("fix: a thing Signed-off-by: Ada Lovelace <ada@example.org>\n")
    assert _failures(commit) == [("a" * 40, MISSING)]


def test_a_second_sign_off_from_another_person_does_not_hide_the_author_s() -> None:
    commit = _commit(
        "fix: a thing\n\n"
        "Signed-off-by: Grace Hopper <grace@example.org>\n"
        "Signed-off-by: Ada Lovelace <ada@example.org>\n"
    )
    assert _failures(commit) == []


def test_only_the_bad_commit_of_two_is_reported() -> None:
    good = _commit("fix: one\n\nSigned-off-by: Ada Lovelace <ada@example.org>\n", sha="1" * 40)
    bad = _commit("fix: two\n", sha="2" * 40)
    assert _failures(good, bad) == [("2" * 40, MISSING)]


def test_a_failure_carries_the_short_sha_and_the_subject_only() -> None:
    commit = _commit("fix: a thing\n\nSECRET-BODY\n", sha="abcdef1234" + "0" * 30)
    shown = [(failure.sha[:7], failure.subject) for failure in dco.check_commits([commit])]
    assert shown == [("abcdef1", "fix: a thing")]
