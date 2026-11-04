"""Masking is a superset of 0.4.0 by construction: what 0.4.0 masked stays masked (release probe6, p6_confirm.py)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from sharpit.engine.capture.sqltrace import SqlTraceRecorder, mask_error
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


def _recorded(text: str) -> str | None:
    recorder = SqlTraceRecorder(MASKER, max_sql_length=10**6)
    recorder.record("SELECT 2", duration_ns=1, thread="t", connection_id=None, success=False, error=Exception(text))
    return recorder.rows()[-1]["errorMessage"]


ERROR_PATHS: dict[str, Callable[[str], str | None]] = {
    "mask_error": ENTRY_POINTS["mask_error"],
    "mask_error_mysql": lambda text: mask_error(MASKER, text, mysql=True),
    "record": _recorded,
}
VENDOR_TOKEN = "xoxb-" + "2qgq5Te2iKkFVekJrsBAT2"
TAIL = "8cr6qmZr5nNRvrYKqvPi"
SQLALCHEMY_ERROR = "sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) x\n[SQL: UPDATE t SET {}]"


# derived: release probe6 fuzz, 16,975 hits: the scan turned a key or a token into ``?`` before the masker read it
@pytest.mark.parametrize("path", ERROR_PATHS)
@pytest.mark.parametrize(
    ("value", "secret"),
    [
        (f"'auth':[FGpmEzFAsxOqeor3Wn52, {TAIL}]", TAIL),
        (f'"pwd":[jkRRpeVtVkPe0qpsyYma, {TAIL}]', TAIL),
        (VENDOR_TOKEN, VENDOR_TOKEN[6:]),
        (f"'pwd': FVZ3JF6P0bJtuGtLqFcg;{TAIL}", TAIL),
        (f"""'token':"KnZy2AQKVS0LSb3MM13n\\"{TAIL}\"""", TAIL),
    ],
    ids=["quoted-key-list", "double-quoted-key-list", "vendor-token", "quoted-pwd", "escaped-quote"],
)
def test_a_statement_is_masked_before_the_scan_changes_its_shape(path: str, value: str, secret: str) -> None:
    shown = ERROR_PATHS[path](SQLALCHEMY_ERROR.format(value))
    assert shown is not None
    assert secret[1:] not in shown


# derived: release probe6 fuzz, rec_off, 2,248 hits: masking first kept a line the driver-value drop would have removed
@pytest.mark.parametrize(
    ("text", "secret"),
    [
        (f'(pymysql.err.OperationalError) (1045, pwd:"first\n{TAIL}")\n[SQL: SELECT 1]\n[parameters: (1,)]', TAIL),
        (f"(pymysql.err.OperationalError) (1045, pwd='{PEM}')\n[SQL: SELECT 1]\n[parameters: (1,)]", PEM_BODY),
        (f'(pymysql.err.OperationalError) (1045, pwd: "first\r\n{TAIL}")\n[SQL: SELECT 1]', TAIL),
        (f'Token expired&"auth"="first {TAIL}"', TAIL),
        (f"chaij3cgvam82vcboinj', '{AWS_KEY}", "chaij3cgvam82vcboinj"),
    ],
    ids=["multi-line", "pem", "crlf", "space-in-value", "before-a-token"],
)
def test_record_drops_driver_values_before_it_masks(text: str, secret: str) -> None:
    shown = _recorded(text)
    assert shown is not None
    assert secret not in shown
