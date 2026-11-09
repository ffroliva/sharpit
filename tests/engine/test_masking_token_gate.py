"""# derived: the token passes cost a Python call per word, so a text that cannot hold a secret skips them.

The gate reads what ``is_secret_value`` reads first, so it can only skip what would have returned the token unchanged.
"""

from __future__ import annotations

from typing import Any

import pytest

from sharpit.engine import masking
from sharpit.engine.masking import MASK, Exposure, Masker

MASKED = Masker(Exposure.MASKED, True)
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJyZXNldCJ9.c2lnbmF0dXJlLWJ5dGVz"
AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
GITHUB_TOKEN = "ghp_" + "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8"
STRIPE_KEY = "sk_live_" + "a1b2c3d4e5f6g7h8i9j0k1l2"


def _counted(monkeypatch: pytest.MonkeyPatch, name: str) -> list[str]:
    calls: list[str] = []
    real = getattr(masking, name)

    def spy(found: Any) -> str:
        calls.append(found[0])
        return real(found)

    monkeypatch.setattr(masking, name, spy)
    return calls


@pytest.mark.parametrize("name", ["_mask_token", "_mask_glued"])
def test_a_statement_with_no_hint_pays_for_no_token(monkeypatch: pytest.MonkeyPatch, name: str):
    calls = _counted(monkeypatch, name)

    MASKED.mask_statement("select * from (select 1 as n) where 0")

    assert calls == []


@pytest.mark.parametrize("name", ["_mask_token", "_mask_glued"])
def test_a_tracked_read_with_no_hint_pays_for_no_token(monkeypatch: pytest.MonkeyPatch, name: str):
    calls = _counted(monkeypatch, name)

    MASKED.mask_spans("select * from (select 1 as n) where 0", False)

    assert calls == []


@pytest.mark.parametrize("value", [JWT, AWS_KEY, GITHUB_TOKEN, STRIPE_KEY], ids=["jwt", "aws", "github", "stripe"])
@pytest.mark.parametrize("shape", ["select {} from t", "GET /reset/{} HTTP/1.1", "{}"], ids=["word", "path", "alone"])
def test_a_secret_the_gate_could_miss_is_still_masked(value: str, shape: str):
    assert value not in (MASKED.mask_statement(shape.format(value)) or "")


def test_a_glued_value_after_a_mask_is_still_read():
    masked = MASKED.mask_text(f"password=x {JWT}.{GITHUB_TOKEN}")

    assert masked is not None
    assert GITHUB_TOKEN not in masked


def test_the_text_with_a_mask_in_it_still_reads_glued_tokens(monkeypatch: pytest.MonkeyPatch):
    calls = _counted(monkeypatch, "_mask_glued")

    MASKED.mask_text(f"a {MASK} b")

    assert calls
