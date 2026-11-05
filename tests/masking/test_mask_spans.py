"""The masker reports which raw characters it hides: one pass chain, tracked only when positions are asked for."""

from __future__ import annotations

import hashlib
import importlib.util
import re
import sys
from pathlib import Path

import pytest

from sharpit.engine import masking
from sharpit.engine.masking import MASK, Exposure, Masker, Tracked

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("_mask_spans_gate", ROOT / "scripts" / "dev" / "masking_gate.py")
assert _spec
assert _spec.loader
gate = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gate
_spec.loader.exec_module(gate)

TOKEN = "sharpit-session-token"
ROWS = gate.corpus(11, 2_000)
MASKERS = {
    "parameters_off": Masker(Exposure.MASKED, True),
    "parameters_on": Masker(Exposure.MASKED, True, capture_parameters=True),
    "own_token": Masker(Exposure.MASKED, True, token=TOKEN),
    "secrets_off": Masker(Exposure.MASKED, False),
    "full": Masker(Exposure.FULL, True, token=TOKEN),
}
# The rule named in A7: the rows `_mask_glued` changes, each hiding more than fa2d51e did. Every other row is pinned
GLUED_ROWS = frozenset(
    (91, 109, 153, 166, 184, 320, 339, 380, 404, 470, 495, 535, 554, 746, 916, 978, 1036, 1044)
    + (1061, 1063, 1229, 1281, 1312, 1344, 1404, 1425, 1475, 1531, 1710, 1794, 1806, 1818, 1883, 1913, 1914)
)
# mask_text on the other rows, at the tree the redesign started from: `git archive fa2d51e src`, SHA-256 of each output
# with a NUL after it. A pin, not a fixture: a changed row shows here and the A7 gate names it
FA2D51E = {
    "parameters_off": "4a9ed25fabf6ec3e41fde124631073e8b2949bbcb2e2265485ebbd7877316dc2",
    "parameters_on": "29de158b3a95449e01220292a66d259f01fe9e264afa4fcd640a240c859db160",
    "own_token": "48e4a6ea68f2f8dd30db9e114a5e8f79c340c9d400adb5abb1caf8a2c62bb514",
    "secrets_off": "248902ac10bae42713a39df91239ed31baac52d298e91d35ecac7ffb91fdaf31",
    "full": "a32ccbf79eafecfcef8789c6f5ad9513317468e5d5f0560ad6caa09e0977a4ed",
}
OFF = MASKERS["parameters_off"]
GITHUB_TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2"


def _kept(text: str, spans: list[tuple[int, int]]) -> str:
    parts: list[str] = []
    cursor = 0
    for start, end in spans:
        parts.append(text[cursor:start])
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


def _spans(masker: Masker, text: str) -> list[tuple[int, int]]:
    spans = masker.mask_spans(text)
    assert spans is not None
    return spans


def _hidden(text: str, masker: Masker = OFF) -> list[str]:
    return [text[start:end] for start, end in _spans(masker, text)]


@pytest.mark.parametrize("name", FA2D51E)
def test_mask_text_output_is_unchanged(name: str) -> None:
    """A guard, green before and after: the chain moved, and what it writes did not."""
    digest = hashlib.sha256()
    for index, row in enumerate(ROWS):
        if index not in GLUED_ROWS:
            output = MASKERS[name].mask_text(f"{row['t']} {TOKEN}")
            assert output is not None
            digest.update(output.encode("utf-8", "surrogatepass") + b"\0")
    assert digest.hexdigest() == FA2D51E[name]


@pytest.mark.parametrize("name", MASKERS)
def test_tracking_changes_no_output(name: str) -> None:
    masker = MASKERS[name]
    for row in ROWS:
        view = Tracked(row["t"])
        masker.mask_spans(row["t"], view=view)
        assert view.text == masker.mask_text(row["t"]), row["t"]


@pytest.mark.parametrize("name", MASKERS)
def test_spans_cover_what_mask_text_removed(name: str) -> None:
    masker = MASKERS[name]
    removed_something = 0
    for row in ROWS:
        output = masker.mask_text(row["t"])
        kept = _kept(row["t"], _spans(masker, row["t"]))
        removed_something += output != row["t"]
        for secret in row["s"]:
            assert gate.leaked(secret, output, kept) is None, row["t"]
    assert removed_something or name == "full"


@pytest.mark.parametrize(
    ("text", "hidden"),
    [
        ("connection refused", []),
        ("password=hunter2 rest\nnext", ["hunter2 rest"]),
        ('"token": "abc def", "id": 1', ['abc def", "id": 1']),
        ("postgres://user:pw@host/db", ["user:pw"]),
        ("see (AKIAABCDEFGHIJKLMNOP).", ["AKIAABCDEFGHIJKLMNOP"]),
        ("failed: Bearer abc123", ["abc123"]),
    ],
    ids=["nothing", "to-the-end-of-the-line", "quoted-pair", "userinfo", "keeps-the-punctuation", "scheme"],
)
def test_spans_name_the_raw_characters(text: str, hidden: list[str]) -> None:
    assert _hidden(text) == hidden


def test_sharpit_token_is_a_span_under_full_exposure() -> None:
    assert _hidden(f"x {TOKEN} y", MASKERS["full"]) == [TOKEN]


def test_a_token_with_a_regex_metacharacter_hides_only_itself() -> None:
    """``a.b`` is a literal: unescaped, ``.`` would also hide ``axb``."""
    masker = Masker(Exposure.FULL, True, token="a.b")
    assert _hidden("x a.b y axb z", masker) == ["a.b"]
    assert masker.mask_text("x a.b y axb z") == f"x {MASK} y axb z"


@pytest.mark.parametrize("value", ["ab*", "*ab", "a*b", "***", "*" * 8])
def test_a_star_in_a_value_is_hidden(value: str) -> None:
    """A mask is stars: a trim that matched them would call a value's own ``*`` kept (Antigravity, spec §8)."""
    assert _kept(f"password={value}", _spans(OFF, f"password={value}")) == "password="


def test_a_star_in_a_quoted_value_is_hidden() -> None:
    assert _kept('"token": "ab*"', _spans(OFF, '"token": "ab*"')) == '"token": ""'


def test_edits_compose_back_to_raw_positions() -> None:
    tracked = Tracked("abcdefgh")
    tracked.apply([(1, 3, "XXXX"), (6, 7, "")])  # b, c and g go
    assert tracked.text == "aXXXXdefh"
    tracked.sub(re.compile("XX"), "Y")  # text the raw never held: nothing more goes
    assert tracked.text == "aYYdefh"
    tracked.apply([(3, 5, "*")])  # d and e go
    assert tracked.text == "aYY*fh"
    assert tracked.hidden() == [(1, 5), (6, 7)]


def test_touching_edits_merge_into_one_span() -> None:
    tracked = Tracked("abcd")
    tracked.apply([(0, 2, "X"), (2, 4, "Y")])
    assert tracked.hidden() == [(0, 4)]


def test_a_view_maps_the_passes_back_to_raw() -> None:
    text = "'a b' password=hunter2"
    view = Tracked(text)
    view.apply([(0, 5, "?")])
    assert view.text == "? password=hunter2"
    spans = OFF.mask_spans(text, view=view)
    assert spans is not None
    assert [text[start:end] for start, end in spans] == ["'a b'", "hunter2"]


def test_text_with_no_positions_hides_all_of_it() -> None:
    """Fail closed: a caller that switched tracking off and asks anyway gets no text shown, never all of it."""
    assert Tracked("abc", track=False).hidden() == [(0, 3)]


def test_an_untracked_text_still_rewrites() -> None:
    tracked = Tracked("abc", track=False)
    tracked.apply([(1, 2, "X")])
    tracked.sub(re.compile("c"), "Y")
    assert tracked.text == "aXY"


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("UPDATE u SET password=? WHERE id=?", f"UPDATE u SET password={MASK} WHERE id=?"),
        ("SELECT a FROM t WHERE b=?", "SELECT a FROM t WHERE b=?"),
        (f"SELECT {GITHUB_TOKEN} FROM t", f"SELECT {MASK} FROM t"),
        ("failed: Bearer abc123", f"failed: Bearer {MASK}"),
        ("x Basic ? y", f"x Basic {MASK} y"),
    ],
    ids=["keeps-the-tail", "nothing", "a-token", "bearer-scheme", "basic-scheme"],
)
def test_mask_statement_runs_no_pass_to_the_end_of_the_line(statement: str, expected: str) -> None:
    assert OFF.mask_statement(statement) == expected


def test_relaxed_spans_stop_at_the_value() -> None:
    text = "password=? WHERE id=?"
    spans = OFF.mask_spans(text, strict=False)
    assert spans is not None
    assert [text[start:end] for start, end in spans] == ["?"]


@pytest.mark.parametrize(
    ("text", "hidden"),
    [("failed: Bearer abc123", ["abc123"]), ("Basic ?", ["?"])],
    ids=["bearer-scheme", "basic-scheme"],
)
def test_relaxed_spans_keep_the_auth_pass(text: str, hidden: list[str]) -> None:
    spans = OFF.mask_spans(text, strict=False)
    assert spans is not None
    assert [text[start:end] for start, end in spans] == hidden


def test_metadata_only_reports_nothing() -> None:
    """``[]`` would read as "nothing to hide": fail open. ``None`` makes a caller short-circuit."""
    masker = Masker(Exposure.METADATA_ONLY, True)
    assert masker.mask_spans("password=hunter2") is None
    assert masker.mask_statement("password=hunter2") is None


@pytest.mark.parametrize(
    "value",
    [
        "eyJabcdefgh.ijklmnopq.rstuvwxyz",
        "-----BEGIN PRIVATE KEY-----",
        "AKIAABCDEFGHIJKLMNOP",
        "ASIAABCDEFGHIJKLMNOP",
        "redis://:pw@host",
        "https://key@sentry.io/1",
        "Server=x;Password=y",
        "https://h/p?token=abc",
        *(f"{prefix}{'a' * 20}" for prefix in masking._VENDOR_PREFIXES),  # noqa: SLF001
    ],
)
def test_the_fast_path_lets_every_secret_shape_through(value: str) -> None:
    """A guard: the one search that replaced two ``any`` loops reads every marker and every vendor prefix."""
    assert masking.is_secret_value(value)


@pytest.mark.parametrize(
    "text",
    [f"x://u@{GITHUB_TOKEN}", f"x://u@{GITHUB_TOKEN}.", f"password=a;{GITHUB_TOKEN}", f"x://u@h/{GITHUB_TOKEN}"],
    ids=["after-userinfo", "before-punctuation", "after-a-value", "in-a-path"],
)
def test_a_token_glued_to_a_mask_is_hidden(text: str) -> None:
    for output in (OFF.mask_text(text), OFF.mask_statement(text), _kept(text, _spans(OFF, text))):
        assert output is not None
        assert GITHUB_TOKEN not in output


def test_the_glued_check_cannot_hide_a_key() -> None:
    assert "hunter3" not in (OFF.mask_text("x://u@h;password=hunter2 hunter3") or "")
