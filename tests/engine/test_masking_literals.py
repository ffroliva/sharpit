"""``scrub_binding_literals``: the user-input literal of a framework message is replaced, nothing else is.

Port of BootUI ``MessageExposure.scrubBindingLiterals``. One parametrized row per pattern, so deleting a pattern from
``_BINDING_LITERALS`` fails the row that names it on the raw literal.
"""

from __future__ import annotations

import re
import time

import pytest

from sharpit.engine import masking
from sharpit.engine.masking import MASK, Exposure, Masker, scrub_binding_literals

RAW = "raw-literal-77"

ROWS = {
    "int": (f"invalid literal for int() with base 16: '{RAW}'", f"invalid literal for int() with base 16: '{MASK}'"),
    "float": (f'could not convert string to float: "{RAW}\'s"', f'could not convert string to float: "{MASK}"'),
    "time-data": (
        f"time data '{RAW}' does not match format '%H:%M'",
        f"time data '{MASK}' does not match format '%H:%M'",
    ),
    "unconverted-data": (f"unconverted data remains:  {RAW}", f"unconverted data remains: {MASK}"),
    "isoformat": (f"Invalid isoformat string: '{RAW}'", f"Invalid isoformat string: '{MASK}'"),
    "enum-string": (f"'{RAW}' is not a valid Color", f"'{MASK}' is not a valid Color"),
    "enum-number": ("918273 is not a valid Color", f"{MASK} is not a valid Color"),
    "pydantic-input-value": (
        f"x [type=int_parsing, input_value='{RAW}', input_type=str]",
        f"x [type=int_parsing, input_value={MASK}, input_type=str]",
    ),
    "pydantic-input-value-unterminated": (f"x [type=t, input_value='{RAW}", f"x [type=t, input_value={MASK}"),
    "pydantic-value-error": (
        f"Value error, bad {RAW} [type=value_error, input_value=1]",
        f"Value error, {MASK} [type=value_error, input_value={MASK}",
    ),
    "pydantic-loc-key": (
        f"1 validation error for M\nc.{RAW}\n  Input should be a valid integer [type=int_parsing, input_value=1]",
        f"1 validation error for M\n{MASK}.{MASK}\n  Input should be a valid integer "
        f"[type=int_parsing, input_value={MASK}",
    ),
    "uuid-found": (
        "invalid character: expected hex, found `Z` at 0 [type=uuid_parsing]",
        f"invalid character: expected hex, found `{MASK}` at 0 [type=uuid_parsing]",
    ),
    "pydantic-assertion": (
        f"Assertion failed, {RAW} [type=assertion_error]",
        f"Assertion failed, {MASK} [type=assertion_error]",
    ),
}


@pytest.mark.parametrize("name", ROWS)
def test_scrubs_each_grammar(name: str) -> None:
    text, expected = ROWS[name]

    assert scrub_binding_literals(text) == expected


def test_every_pattern_has_a_row_that_fails_without_it() -> None:
    for index, (pattern, _) in enumerate(masking._BINDING_LITERALS):
        reduced = masking._BINDING_LITERALS[:index] + masking._BINDING_LITERALS[index + 1 :]
        scrubbed = []
        for text, _ in ROWS.values():
            for rest, replacement in reduced:
                text = rest.sub(replacement, text)
            scrubbed.append(text)

        assert any(RAW in text or "918273" in text or "found `Z`" in text for text in scrubbed), pattern.pattern


@pytest.mark.parametrize("exposure", [Exposure.MASKED, Exposure.METADATA_ONLY])
def test_real_pydantic_dict_key_is_hidden_outside_full(exposure: Exposure) -> None:
    pydantic = pytest.importorskip("pydantic")

    class Model(pydantic.BaseModel):
        counts: dict[str, int]

    with pytest.raises(pydantic.ValidationError) as caught:
        Model(counts={"planted-key-5": "x"})
    message = str(caught.value)

    shown = Masker(exposure, True).scrub_literals(message)

    assert shown is not None
    assert "planted-key-5" not in shown
    assert f"{MASK}.{MASK}" in shown
    assert Masker(Exposure.FULL, True).scrub_literals(message) == message
    assert "counts.planted-key-5" in message


def test_scrub_returns_none_and_empty_text_unchanged() -> None:
    assert scrub_binding_literals(None) is None
    assert scrub_binding_literals("") == ""


def test_scrub_is_idempotent() -> None:
    once = scrub_binding_literals(ROWS["int"][0])

    assert scrub_binding_literals(once) == once


def test_masker_scrubs_outside_full_only() -> None:
    text = ROWS["int"][0]

    assert Masker(Exposure.MASKED, True).scrub_literals(text) == ROWS["int"][1]
    assert Masker(Exposure.MASKED, False).scrub_literals(text) == ROWS["int"][1]
    assert Masker(Exposure.METADATA_ONLY, True).scrub_literals(text) == ROWS["int"][1]
    assert Masker(Exposure.FULL, False).scrub_literals(text) == text
    assert Masker(Exposure.MASKED, True).scrub_literals(None) is None


@pytest.mark.parametrize(
    "hostile",
    [
        "invalid literal for int() with base 10: '" + "a" * 2_000_000,
        "time data '" + "\\'" * 1_000_000,
        "input_value=" * 400_000,
        "Value error, " * 400_000,
        "'a" * 1_000_000 + " is not a valid X",
        "\\'" * 1_000_000 + " is not a valid X",
        "unconverted data remains: " * 300_000,
        "1" * 2_000_000 + " is not a valid X",
    ],
    ids=["int", "time", "input-value", "value-error", "enum-quotes", "enum-escapes", "unconverted", "enum-digits"],
)
def test_exception_scrub_is_bounded_for_huge_input(hostile: str) -> None:
    started = time.perf_counter()

    scrubbed = scrub_binding_literals(hostile)

    assert scrubbed is not None
    assert time.perf_counter() - started < 3


@pytest.mark.parametrize("exposure", [Exposure.MASKED, Exposure.METADATA_ONLY])
def test_real_pydantic_root_dict_key_is_hidden_outside_full(exposure: Exposure) -> None:
    pydantic = pytest.importorskip("pydantic")
    with pytest.raises(pydantic.ValidationError) as caught:
        pydantic.TypeAdapter(dict[str, int]).validate_python({"my_secret_token_key": "not-an-int"})
    message = str(caught.value)

    shown = Masker(exposure, True).scrub_literals(message)

    assert shown is not None
    assert "my_secret_token_key" not in shown
    assert Masker(Exposure.FULL, True).scrub_literals(message) == message


def test_request_locations_and_indices_are_kept() -> None:
    text = f"2 validation errors for M\nbody.0.{RAW}\n  Input should be a valid integer [type=int_parsing]"

    assert f"\nbody.0.{MASK}\n" in str(scrub_binding_literals(text))


def test_crlf_text_keeps_its_line_endings_and_indices() -> None:
    text = (
        "1 validation error for M\r\nitems.0.name\r\n  Input should be a valid integer "
        f"[type=int_parsing, input_value='{RAW}', input_type=str]\r\n    For further information"
    )

    assert scrub_binding_literals(text) == (
        "1 validation error for M\r\n"
        f"{MASK}.0.{MASK}\r\n  Input should be a valid integer "
        f"[type=int_parsing, input_value={MASK}, input_type=str]\r\n    For further information"
    )


_FOUND_AT_REFERENCE = re.compile(r"(\bfound `)[^\r\n]*?(` at \d+)")  # the quadratic pattern the scan replaced


def _reference(text: str) -> str:
    return _FOUND_AT_REFERENCE.sub(lambda m: f"{m[1]}{MASK}{m[2]}", text)


@pytest.mark.parametrize(
    "text",
    [
        "found `abc` at 5",
        "found `a` at 1 and found `b` at 22",
        "found `` at 3",
        "found `a found `b` at 7",
        "x\r\nfound `a` at 1\r\nfound `b` at 2\rfound `c` at 3\nend",
        "afound `a` at 1",
        "found `abc at 5",
        "found `abc` at x",
        "found `abc`\nat 5",
        "found `a` at 1 found `b",
        "found `a` at 12345` at 6",
        "no match here",
        "",
    ],
)
def test_found_at_scan_matches_what_the_lazy_pattern_matched(text: str) -> None:
    assert scrub_binding_literals(text) == _reference(text) or text == ""
    assert masking._UUID_CHAR.sub(lambda m: f"{m[1]}{MASK}{m[2]}", text) == _reference(text)


def test_found_at_scan_matches_the_lazy_pattern_on_random_text() -> None:
    import random

    rng = random.Random(7)
    pieces = ["found `", "` at ", "7", "x", "\n", "\r\n", " ", "`", "found", "at 12"]
    for _ in range(3000):
        text = "".join(rng.choice(pieces) for _ in range(rng.randint(0, 14)))
        assert masking._UUID_CHAR.sub(lambda m: f"{m[1]}{MASK}{m[2]}", text) == _reference(text), repr(text)


@pytest.mark.parametrize("unit", ["found `", "found `x` at", "found `\n"])
def test_found_at_scan_is_linear_on_a_64_kb_message(unit: str) -> None:
    text = unit * (64_000 // len(unit))
    started = time.perf_counter()
    scrub_binding_literals(text)

    assert time.perf_counter() - started < 0.1
