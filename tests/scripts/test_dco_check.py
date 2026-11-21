"""scripts/ci/dco_check.py: every non-merge, non-Dependabot commit carries a Signed-off-by trailer of its author."""

from __future__ import annotations

import json
import re
import socket
import subprocess
from typing import Any

import pytest
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


# main(): the command line the workflow runs. subprocess.run is replaced, so nothing reaches the network.

REPAIR = "git rebase --signoff <base> && git push --force-with-lease"
SIGNED = "fix: ok\n\nSigned-off-by: Ada Lovelace <ada@example.org>\n"


class _Gh:
    """A stand-in for subprocess.run that records the call and answers as `gh api` would."""

    def __init__(self, stdout: str = "[]", returncode: int = 0, stderr: str = "") -> None:
        self.result = subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((args, kwargs))
        return self.result


def _run_main(monkeypatch: pytest.MonkeyPatch, gh: _Gh, *, repo: str = "owner/repo", number: str = "7") -> int:
    monkeypatch.setattr(dco.subprocess, "run", gh)
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setenv("REPO", repo)
    monkeypatch.setenv("PR_NUMBER", number)
    return dco.main()


def test_main_exits_one_and_prints_the_repair_when_a_commit_fails(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gh = _Gh(json.dumps([_commit("fix: a thing\n")]))
    assert _run_main(monkeypatch, gh) == 1
    assert REPAIR in capsys.readouterr().out


def test_main_prints_one_line_per_failing_commit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    commits = [_commit("fix: one\n", sha="1" * 40), _commit(SIGNED, sha="2" * 40), _commit("fix: two\n", sha="3" * 40)]
    _run_main(monkeypatch, _Gh(json.dumps(commits)))
    lines = [line for line in capsys.readouterr().out.splitlines() if re.match(r"[0-9a-f]{7} ", line)]
    assert lines == [f"1111111 fix: one - {MISSING}", f"3333333 fix: two - {MISSING}"]


def test_main_never_prints_a_message_body(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    gh = _Gh(json.dumps([_commit("fix: a thing\n\nSECRET-BODY\n")]))
    _run_main(monkeypatch, gh)
    assert "SECRET-BODY" not in capsys.readouterr().out


def test_main_strips_control_characters_from_a_subject(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    gh = _Gh(json.dumps([_commit("fix: \x1b[31mred\rpart\n", sha="4" * 40)]))
    _run_main(monkeypatch, gh)
    lines = [line for line in capsys.readouterr().out.splitlines() if line.startswith("4444444 ")]
    assert lines == [f"4444444 fix:  [31mred part - {MISSING}"]


def test_main_exits_zero_when_every_commit_is_signed(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run_main(monkeypatch, _Gh(json.dumps([_commit(SIGNED)]))) == 0


def test_main_exits_zero_for_a_pull_request_without_commits(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run_main(monkeypatch, _Gh("[]")) == 0


def test_main_reads_every_page_of_a_paginated_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = json.dumps([_commit(SIGNED, sha="1" * 40)]) + json.dumps([_commit("fix: two\n", sha="2" * 40)])
    assert _run_main(monkeypatch, _Gh(pages)) == 1


def test_main_asks_gh_for_the_commit_list_without_a_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    gh = _Gh()
    _run_main(monkeypatch, gh)
    args, kwargs = gh.calls[0]
    assert (args, kwargs.get("shell")) == (["gh", "api", "--paginate", "repos/owner/repo/pulls/7/commits"], False)


def test_main_opens_no_socket_of_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the check opened a socket")

    monkeypatch.setattr(socket, "socket", refuse)
    assert _run_main(monkeypatch, _Gh(json.dumps([_commit(SIGNED)]))) == 0


def test_main_fails_closed_when_gh_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run_main(monkeypatch, _Gh("[]", returncode=1, stderr="HTTP 404")) == 2


def test_main_fails_closed_when_the_answer_is_not_a_commit_list(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run_main(monkeypatch, _Gh('{"message": "Not Found"}')) == 2


@pytest.mark.parametrize(("repo", "number"), [("", "7"), ("owner", "7"), ("owner/repo", "x"), ("owner/repo;id", "7")])
def test_main_rejects_a_malformed_environment_before_calling_gh(
    monkeypatch: pytest.MonkeyPatch, repo: str, number: str
) -> None:
    gh = _Gh()
    _run_main(monkeypatch, gh, repo=repo, number=number)
    assert gh.calls == []
