import pytest

from sharpit.engine.collectors.config.dotenv import parse_dotenv


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("A=1", {"A": "1"}),
        ("export A=1", {"A": "1"}),
        ("A='x y'", {"A": "x y"}),
        ('A="x y"', {"A": "x y"}),
        ('A="l1\\nl2"', {"A": "l1\nl2"}),
        ("A='l1\\nl2'", {"A": "l1\\nl2"}),
        ("# comment\nA=1  # trailing\nB=2", {"A": "1", "B": "2"}),
        ('A="x # y"', {"A": "x # y"}),
        ('A=1\nB=${A}-b\nC="${B}!"', {"A": "1", "B": "1-b", "C": "1-b!"}),
        ("A=${HOME_X}/bin\nB='${HOME_X}'", {"A": "/root/bin", "B": "${HOME_X}"}),
        ("A=${NOPE:-fallback}\nB=${NOPE}", {"A": "fallback", "B": ""}),
        ("\n  \nnot a pair\nA=1\n", {"A": "1"}),
        ("A=", {"A": ""}),
    ],
)
def test_grammar(text: str, expected: dict[str, str]) -> None:
    assert parse_dotenv(text, environ={"HOME_X": "/root"}) == expected


def test_environ_not_mutated() -> None:
    env = {"E": "1"}
    parse_dotenv("A=${E}", environ=env)
    assert env == {"E": "1"}


def test_earlier_key_wins_over_environ() -> None:
    assert parse_dotenv("E=file\nA=${E}", environ={"E": "env"})["A"] == "file"
