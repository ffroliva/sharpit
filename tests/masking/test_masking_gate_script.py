"""``scripts/dev/masking_gate.py``: the comparator and the corpus, as pure functions. No tree is archived here.

The gate is only worth its verdict if a regression it exists to find is counted: these tests plant one.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("_script_masking_gate", ROOT / "scripts" / "dev" / "masking_gate.py")
assert _spec
assert _spec.loader
gate = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gate
_spec.loader.exec_module(gate)

SECRET = "Qx7LmN2pRs9TvWy4ZaB6cD"  # 22 characters, none of them in the corpus's fixed text
# sha256 of the first 3,000 rows of probe8/gen.py, seed 11, printed as it prints them: the RCA's counts come from it
P2_GEN_SEED_11 = "a2acfc4df58c65b2cd76292548b59c72d6a0d6899041588e04ace7598ee54ddd"


def test_the_corpus_is_p2_gens_byte_for_byte() -> None:
    lines = "".join(json.dumps(row) + "\n" for row in gate.corpus(11, 3000))
    assert hashlib.sha256(lines.encode()).hexdigest() == P2_GEN_SEED_11


def test_the_corpus_is_seeded() -> None:
    assert gate.corpus(5, 50) == gate.corpus(5, 50)
    assert gate.corpus(5, 50) != gate.corpus(6, 50)


def test_a_secret_shown_whole_is_found() -> None:
    assert gate.shown(SECRET, f"a {SECRET} b") == SECRET


def test_a_substring_of_a_long_secret_is_found() -> None:
    """Spec A2 r2, r3: eight characters of it, wherever they start, show it; the old step of 4 over 14 missed these."""
    assert gate.shown(SECRET, f"x{SECRET[3:11]}y") == SECRET[3:11]
    assert gate.shown(SECRET, f"x{SECRET[13:21]}y") == SECRET[13:21]


def test_seven_characters_of_a_secret_are_not_found() -> None:
    assert gate.shown(SECRET, f"x{SECRET[3:10]}y") is None


def test_the_corpus_own_fixed_text_is_not_a_secret() -> None:
    assert gate.shown("sk_live_" + "Zz" * 12, "prefix sk_live_ only") is None


def test_a_planted_baseline_reports_a_hit() -> None:
    """The baseline hid the secret; the candidate shows it: one hit, on that surface only."""
    old = {"trace": "(x) ******"}
    new = {"trace": f"(x) {SECRET}"}
    assert +gate.a2_hits([SECRET], old, new) == {"trace": 1}


def test_a_secret_the_baseline_also_showed_is_no_regression() -> None:
    shown = {"trace": f"(x) {SECRET}"}
    assert not +gate.a2_hits([SECRET], shown, shown)


def test_a_secret_is_judged_on_its_own_surface() -> None:
    """``mask_text`` hid it, the trace path did not: judging traces by ``mask_text`` hid 2,270 regressions."""
    old = {"err_off": "******", "trace": SECRET}
    new = {"err_off": SECRET, "trace": SECRET}
    assert +gate.a2_hits([SECRET], old, new) == {"err_off": 1}


def test_an_unchanged_output_is_not_a_difference() -> None:
    assert gate.a7_row([SECRET], "a ******", "a ******") == (False, False)


def test_an_output_that_hides_more_differs_without_a_secret_newly_shown() -> None:
    assert gate.a7_row([SECRET], f"a {SECRET[:7]} b", "a ****** b") == (True, False)


def test_an_output_that_shows_a_secret_newly_is_counted() -> None:
    assert gate.a7_row([SECRET], "a ******", f"a {SECRET}") == (True, True)


@pytest.mark.parametrize("mode", ["a2", "a7"])
def test_each_gate_names_its_baseline(mode: str) -> None:
    assert gate.BASELINES[mode] == {"a2": "v0.4.0", "a7": "fa2d51e"}[mode]


def test_a_checkout_is_used_in_place(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    assert gate.export(str(tmp_path), tmp_path / "unused") == tmp_path.resolve() / "src"


def test_a_composite_secret_comes_back_though_the_baseline_showed_its_host() -> None:
    """C1: ``https://host/<a>?password=<b>`` with ``<b>`` hidden before and shown now is a hit."""
    secret = "https://api.x.io/" + "Qx7LmN2pRs9TvWy4ZaB6" + "?password=" + "Hk3Jd8Fg5Ls1Zp0Wm2Xc"
    old = {"trace": secret.replace("Hk3Jd8Fg5Ls1Zp0Wm2Xc", "******")}
    assert +gate.a2_hits([secret], old, {"trace": secret}) == {"trace": 1}


def test_a_secret_shown_in_part_before_and_whole_now_is_a_hit() -> None:
    old = {"trace": f"x {SECRET[:8]} y"}
    assert +gate.a2_hits([SECRET], old, {"trace": f"x {SECRET} y"}) == {"trace": 1}


def test_a_window_the_baseline_also_showed_is_no_regression() -> None:
    assert not +gate.a2_hits([SECRET], {"trace": f"x{SECRET[3:11]}"}, {"trace": f"y{SECRET[3:11]}"})


BASELINE_NAMES = ["traces._sql_message"]
CANDIDATE_NAMES = ["sqltrace.mask_error"]


def test_the_baseline_resolves_to_what_0_4_0_ran() -> None:
    assert gate.resolve("baseline", [*BASELINE_NAMES, "sqltrace.mask_error"]) == {
        "logs": "masker.mask_text",
        "trace": "traces._sql_message",
    }


def test_a_baseline_without_sql_message_is_an_error_not_mask_text() -> None:
    with pytest.raises(LookupError, match="_sql_message"):
        gate.resolve("baseline", ["sqltrace.mask_error"])


def test_a_candidate_without_mask_error_is_an_error_not_mask_text() -> None:
    with pytest.raises(LookupError, match="mask_error"):
        gate.resolve("candidate", ["traces._sql_message", "sqltrace.trace_message"])


def test_a_candidate_resolves_its_own_trace_function() -> None:
    assert gate.resolve("candidate", CANDIDATE_NAMES) == {"logs": "sqltrace.mask_error", "trace": "sqltrace.mask_error"}


def _a7(old: list[str], new: list[str], **kwargs: object) -> int:
    data = [{"t": text, "s": [SECRET]} for text in old]
    before = [{"text_off": text, "text_on": text} for text in old]
    after = [{"text_off": text, "text_on": text} for text in new]
    return gate.a7_report(data, before, after, **kwargs)  # type: ignore[arg-type]


HIDDEN = ["a ******", "b ******", "c ******"]


def test_a7_passes_an_identical_tree() -> None:
    assert _a7(HIDDEN, HIDDEN) == 0


def test_a7_fails_a_planted_leak() -> None:
    assert _a7(HIDDEN, [f"a {SECRET}", "b ******", "c ******"]) == 1


def test_a7_fails_a_planted_blank() -> None:
    """I3: every output blanked differs, no secret is shown, and the gate must still fail."""
    assert _a7(HIDDEN, ["?", "?", "?"]) == 1


def test_a7_passes_a_difference_a_named_rule_covers() -> None:
    assert _a7(HIDDEN, ["a ******", "b *****", "c ******"], allowed=2, rule="an example rule") == 0


def test_a7_fails_more_differences_than_the_rule_covers() -> None:
    assert _a7(HIDDEN, ["?", "?", "c ******"], allowed=2, rule="an example rule") == 1


def test_a7_fails_an_allowance_with_no_rule_named() -> None:
    assert _a7(HIDDEN, ["a *****", "b ******", "c ******"], allowed=2) == 1
