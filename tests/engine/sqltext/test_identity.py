import hashlib
import re

import pytest

from sharpit.engine.activation import ActivationStatus
from sharpit.engine.capture.sqlinsights import insights_report
from sharpit.engine.capture.sqlscan import normalize
from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.capture.statement import masked_shape
from sharpit.engine.context import SharpitContext
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import Dialect
from sharpit.settings import load_settings

KEY = b"k" * 32
OPAQUE = re.compile(r"[0-9a-f]{64}")
HIDDEN_NAME = 'select "id" from "users"'


def _keyed(key: bytes = KEY) -> Masker:
    masker = Masker(Exposure.MASKED, True)
    masker.identity_key = key
    return masker


def test_two_tables_stay_two_groups_on_sqlite() -> None:
    recorder = SqlTraceRecorder(_keyed())
    for sql in (HIDDEN_NAME, 'select "id" from "orders"'):
        recorder.record(sql, duration_ns=1, thread="main", connection_id=None, dialect=Dialect.SQLITE)
    assert recorder.aggregate_count == 2


def test_a_sqlite_id_is_opaque_when_keyed() -> None:
    identity = masked_shape(_keyed(), HIDDEN_NAME, Dialect.SQLITE).fingerprint
    assert identity is not None
    assert OPAQUE.fullmatch(identity), f"not an opaque id: {identity!r}"
    assert "users" not in identity


def test_a_sqlite_id_shown_by_insights_is_opaque() -> None:
    recorder = SqlTraceRecorder(_keyed())
    recorder.record(HIDDEN_NAME, duration_ns=1_000_000, thread="main", connection_id=None, dialect=Dialect.SQLITE)
    [row] = insights_report(recorder, None, None)["statements"]
    assert OPAQUE.fullmatch(row["id"]), f"not an opaque id: {row['id']!r}"


def test_a_sqlite_id_is_never_a_plain_hash_of_the_shape() -> None:
    identity = masked_shape(_keyed(), HIDDEN_NAME, Dialect.SQLITE).fingerprint
    shape = normalize(HIDDEN_NAME, Dialect.UNSUPPORTED).fingerprint
    assert shape is not None
    assert identity != hashlib.sha256(shape.encode()).hexdigest()


def test_a_sqlite_id_moves_with_the_key() -> None:
    first = masked_shape(_keyed(b"a" * 32), HIDDEN_NAME, Dialect.SQLITE).fingerprint
    second = masked_shape(_keyed(b"b" * 32), HIDDEN_NAME, Dialect.SQLITE).fingerprint
    assert first != second


@pytest.mark.parametrize("dialect", [Dialect.POSTGRESQL, Dialect.MYSQL_FAMILY, Dialect.UNSUPPORTED])
def test_a_key_moves_no_other_dialects_id(dialect: Dialect) -> None:
    keyed = masked_shape(_keyed(), "select id from users where a = 1", dialect)
    plain = masked_shape(Masker(Exposure.MASKED, True), "select id from users where a = 1", dialect)
    assert keyed == plain


def test_a_context_takes_its_key_from_the_settings() -> None:
    settings = load_settings({"identity_key": "x" * 32}, {})
    activation = ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ())
    assert SharpitContext(settings, activation, None).masker.identity_key == b"x" * 32
