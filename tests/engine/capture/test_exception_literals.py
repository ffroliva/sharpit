"""Binding literals in exception and cause messages are scrubbed outside ``FULL`` (port of BootUI 2.5.0).

BootUI's ``ExceptionsService.displayMessage`` masks a message by the exposure policy and then scrubs the user-input
literals of the framework messages that quote them (``MessageExposure.scrubBindingLiterals``). sharpit reads the same
rule at projection time, for the message grammars CPython 3.12 to 3.14 and Pydantic v2 emit. Each grammar has one test
that names it, so deleting its pattern fails that test on the raw literal. A plain literal in an arbitrary
``RuntimeError`` is not a binding-literal form and is never claimed.
"""

from __future__ import annotations

import datetime
import enum
from collections.abc import Callable
from typing import Any

import pytest

from sharpit.engine.capture.exceptions import ExceptionStore
from sharpit.engine.masking import MASK, Exposure, Masker

SENTINEL = "ordinary-sentinel-91"


class Color(enum.Enum):
    RED = 1


def _raised(factory: Callable[[], object]) -> BaseException:
    try:
        factory()
    except BaseException as exc:  # noqa: BLE001
        return exc
    raise AssertionError("the call did not raise")


def _store(exposure: Exposure = Exposure.MASKED, mask_secrets: bool = True) -> ExceptionStore:
    return ExceptionStore(100, 25, 50, Masker(exposure, mask_secrets), application=lambda: None)


def _shown(exc: BaseException, store: ExceptionStore | None = None) -> str | None:
    store = store or _store()
    store.record(exc, "log", None, "main")
    groups: list[dict[str, Any]] = store.report()["groups"]
    return groups[0]["message"]


GRAMMARS = {
    "int": (lambda: int(SENTINEL), f"invalid literal for int() with base 10: '{MASK}'"),
    "float": (lambda: float(SENTINEL), f"could not convert string to float: '{MASK}'"),
    "strptime": (
        lambda: datetime.datetime.strptime(SENTINEL, "%Y-%m-%d"),
        f"time data '{MASK}' does not match format '%Y-%m-%d'",
    ),
    "unconverted": (
        lambda: datetime.datetime.strptime(f"2026-01-01 {SENTINEL}", "%Y-%m-%d"),
        f"unconverted data remains: {MASK}",
    ),
    "isoformat": (lambda: datetime.date.fromisoformat(SENTINEL), f"Invalid isoformat string: '{MASK}'"),
    "enum": (lambda: Color(SENTINEL), f"'{MASK}' is not a valid Color"),
}


# ported: ExceptionsServiceTests.scrubsBoundaryMapKeysAndAdversarialFrameworkMessagesInMaskedMode
def test_scrubs_int_binding_literal() -> None:
    shown = _shown(_raised(lambda: int(SENTINEL)))

    assert shown == f"invalid literal for int() with base 10: '{MASK}'"


# ported: ExceptionsServiceTests.scrubsBoundaryMapKeysAndAdversarialFrameworkMessagesInMaskedMode
@pytest.mark.parametrize("name", GRAMMARS)
def test_scrubs_supported_python_binding_messages(name: str) -> None:
    raiser, expected = GRAMMARS[name]

    shown = _shown(_raised(raiser))

    assert shown == expected


def test_scrubs_a_quoted_literal_with_escapes_and_a_bytes_prefix() -> None:
    quoted = _raised(lambda: int("a'b\"c\\d\ne"))
    as_bytes = _raised(lambda: int(b"raw-bytes-91"))

    assert _shown(quoted) == f"invalid literal for int() with base 10: '{MASK}'"
    assert _shown(as_bytes, _store()) == f"invalid literal for int() with base 10: '{MASK}'"


def test_scrubs_numeric_enum_input() -> None:
    shown = _shown(_raised(lambda: Color(918273645)))

    assert shown == f"{MASK} is not a valid Color"


def test_scrubs_pydantic_rendered_message_only() -> None:
    pydantic = pytest.importorskip("pydantic")

    class Payload(pydantic.BaseModel):
        count: int
        note: str

        @pydantic.field_validator("note")
        @classmethod
        def _check(cls, value: str) -> str:
            raise ValueError(f"bad note {value}")

    shown = _shown(_raised(lambda: Payload.model_validate({"count": SENTINEL, "note": f"{SENTINEL}-note"})))

    assert shown is not None
    assert SENTINEL not in shown
    assert "input_type=str" in shown
    assert "Input should be a valid integer" in shown
    assert f"Value error, {MASK} [type=value_error" in shown


def test_scrubs_pydantic_input_value_that_repeats_the_terminator() -> None:
    text = f"1 validation error for M\nn\n  bad [type=x, input_value='{SENTINEL}, input_type=int', input_type=str]\n"

    shown = _shown(ValueError(text))

    assert shown is not None
    assert SENTINEL not in shown
    assert shown.endswith(f"input_value={MASK}, input_type=str]\n")


def test_scrubs_pydantic_value_error_across_lines() -> None:
    text = f"1 validation error for M\nn\n  Value error, first {SENTINEL}\nsecond {SENTINEL}"
    text += " [type=value_error, input_value=1]"

    shown = _shown(ValueError(text))

    assert shown is not None
    assert SENTINEL not in shown


def test_scrubs_each_exception_group_and_cause_message() -> None:
    cause = ValueError(f"invalid literal for int() with base 10: 'cause-{SENTINEL}'")
    context_exc = ValueError(f"could not convert string to float: 'context-{SENTINEL}'")
    leaf_a = ValueError(f"invalid literal for int() with base 10: 'leaf-a-{SENTINEL}'")
    leaf_b = ValueError(f"invalid literal for int() with base 10: 'leaf-b-{SENTINEL}'")
    try:
        try:
            raise context_exc
        except ValueError:
            raise ExceptionGroup("group", [leaf_a, leaf_b]) from cause
    except ExceptionGroup as exc:
        recorded = exc
    store = _store()

    store.record(recorded, "log", None, "main")
    gid = store.report()["groups"][0]["id"]
    detail = store.detail(gid)

    assert detail is not None
    assert SENTINEL not in repr(detail["group"])
    assert SENTINEL not in repr(detail["causes"])
    assert SENTINEL not in repr(store.report())


def test_exception_message_exposure_modes() -> None:
    exc = _raised(lambda: int(SENTINEL))
    plain = "invalid literal for int() with base 10: '" + SENTINEL + "'"

    assert _shown(exc, _store(Exposure.MASKED)) == f"invalid literal for int() with base 10: '{MASK}'"
    assert _shown(exc, _store(Exposure.METADATA_ONLY)) is None
    assert _shown(exc, _store(Exposure.FULL)) == plain


def test_exception_message_follows_the_live_exposure() -> None:
    store = _store(Exposure.FULL)
    exc = _raised(lambda: int(SENTINEL))
    store.record(exc, "log", None, "main")
    store.masker = Masker(Exposure.MASKED, True)

    shown = store.report()["groups"][0]["message"]

    assert SENTINEL not in shown


def test_scrub_mask_order_and_mask_secrets_false() -> None:
    secret = _raised(lambda: int("password=hunter2"))
    keyed = ValueError("Authorization: Bearer abcdef0123456789abcdef and 'x' is not a valid Color")

    open_masker = _store(Exposure.MASKED, mask_secrets=False)

    assert _shown(secret, open_masker) == f"invalid literal for int() with base 10: '{MASK}'"
    assert _shown(secret, _store()) == f"invalid literal for int() with base 10: '{MASK}'"
    assert _shown(keyed, _store(Exposure.MASKED, mask_secrets=False)) == (
        f"Authorization: Bearer abcdef0123456789abcdef and '{MASK}' is not a valid Color"
    )


def test_preserves_arbitrary_runtime_error_message() -> None:
    shown = _shown(RuntimeError(f"cannot process '{SENTINEL}' right now"))

    assert shown == f"cannot process '{SENTINEL}' right now"


@pytest.mark.parametrize(
    "message",
    [
        "badly formed hexadecimal UUID string",
        "[<class 'decimal.ConversionSyntax'>]",
        "complex() arg is a malformed string",
        "Expecting value: line 1 column 7 (char 6)",
        "the 'name' is not valid here",
        "value is not a valid choice",
        "Input should be a valid list[int] or dict[str, Any]",
        "unconverted data remains in the buffer",
        "invalid literal for int() with base 10",
        "Invalid isoformat string",
        "time data and format differ",
        "input_value is a pydantic term",
    ],
)
def test_preserves_binding_message_near_misses(message: str) -> None:
    assert _shown(ValueError(message)) == message


def test_does_not_add_notes_or_args_to_message_projection() -> None:
    exc = ValueError("plain failure")
    exc.add_note(f"note {SENTINEL}")
    exc.args = ("plain failure", {"payload": SENTINEL}, SENTINEL.encode())

    shown = _shown(exc)

    assert shown == "plain failure"
