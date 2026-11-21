"""``scrub_binding_literals``: the user-input literal of a framework message is replaced, nothing else is.

Port of BootUI ``MessageExposure.scrubBindingLiterals``. One parametrized row per pattern, so deleting a pattern from
``_BINDING_LITERALS`` fails the row that names it on the raw literal.
"""

from __future__ import annotations

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

        assert any(RAW in text or "918273" in text for text in scrubbed), pattern.pattern


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
