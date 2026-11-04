"""Masking is a superset of 0.4.0 by construction: what 0.4.0 masked stays masked (release probe6, p6_confirm.py)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from sharpit.engine.capture.sqltrace import mask_error
from sharpit.engine.masking import Exposure, Masker

MASKER = Masker(Exposure.MASKED, True)
PEM_BODY = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC"
PEM = f"-----BEGIN PRIVATE KEY-----\n{PEM_BODY}\n-----END PRIVATE KEY-----"
AWS_KEY = "AKIA" + "ABCDEFGHIJKLMNOP"
GITHUB_TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2"
STRIPE_KEY = "sk_live_" + "Z9y8X7w6V5u4T3s2R1q0"

ENTRY_POINTS: dict[str, Callable[[str], str | None]] = {
    "mask_text": MASKER.mask_text,
    "mask_error": lambda text: mask_error(MASKER, text),
}


@pytest.mark.parametrize("entry", ENTRY_POINTS)
@pytest.mark.parametrize(
    "text",
    [
        f'private_key="{PEM}"',
        f"private_key='{PEM}'",
        f'"private_key": "{PEM}"',
        f"'private_key': '{PEM}'",
        f'{{"private_key": "{PEM}", "n": 1}}',
        f'could not load private_key="{PEM}" from disk',
        f'password: "first\n{PEM_BODY}\nlast"',
    ],
    ids=["double", "single", "json", "dict-repr", "json-object", "in-a-sentence", "colon"],
)
def test_a_multi_line_quoted_value_is_masked_on_every_line(entry: str, text: str) -> None:
    shown = ENTRY_POINTS[entry](text)
    assert shown is not None
    assert PEM_BODY not in shown


@pytest.mark.parametrize("entry", ENTRY_POINTS)
@pytest.mark.parametrize(
    ("text", "secret"),
    [
        (f"{AWS_KEY}:password=abc", AWS_KEY),
        (f"{GITHUB_TOKEN}:password=abc", GITHUB_TOKEN),
        (f"{STRIPE_KEY}:token=abc", STRIPE_KEY),
        (f"sent {AWS_KEY}:password=abc upstream", AWS_KEY),
        (f"{GITHUB_TOKEN}=password=abc", GITHUB_TOKEN),
    ],
    ids=["aws", "github", "stripe", "in-a-sentence", "equals"],
)
def test_a_secret_inside_a_token_is_masked(entry: str, text: str, secret: str) -> None:
    shown = ENTRY_POINTS[entry](text)
    assert shown is not None
    assert secret not in shown
