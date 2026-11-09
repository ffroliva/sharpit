"""Task 35 council (second reviewer, Critical): METADATA_ONLY never shows more of a statement than MASKED.

A value in code position (a bare word after a sensitive key, a token shape, sharpit's own token) is no literal, so the
scan keeps it and only the masker's statement pass hides it. The shape under METADATA_ONLY skipped that pass.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import Dialect, statement_shape
from sharpit.fastapi.adapter import SharpitHandle

pytestmark = pytest.mark.needs_sqlalchemy
sa = pytest.importorskip("sqlalchemy")

OWN_TOKEN = "ownconsoletokenq5f3a9c"
VALUES = {
    "key": "hunter2plain",
    "token": "ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8",
    "own_token": OWN_TOKEN,
}
STATEMENT = f"SELECT 1 FROM u WHERE password = {VALUES['key']} AND k = {VALUES['token']} AND c = {OWN_TOKEN} AND x = 1"
DIALECTS = [Dialect.POSTGRESQL, Dialect.MYSQL_FAMILY, Dialect.SQLITE]
DIALECT_IDS = ["postgresql", "mysql_family", "sqlite"]


def _shape(exposure: Exposure, dialect: Dialect) -> tuple[str, str | None]:
    shape = statement_shape(Masker(exposure, True, OWN_TOKEN, identity_key=b"k" * 32), STATEMENT, dialect)
    return shape.text, shape.fingerprint


@pytest.mark.parametrize("value", sorted(VALUES))
@pytest.mark.parametrize("dialect", DIALECTS, ids=DIALECT_IDS)
def test_metadata_only_shape_text_hides_what_masked_hides(dialect: Dialect, value: str) -> None:
    masked, _ = _shape(Exposure.MASKED, dialect)
    assert VALUES[value] not in masked  # the control: MASKED hides it
    text, _ = _shape(Exposure.METADATA_ONLY, dialect)
    assert VALUES[value] not in text


@pytest.mark.parametrize("value", sorted(VALUES))
@pytest.mark.parametrize("dialect", DIALECTS, ids=DIALECT_IDS)
def test_metadata_only_shape_identity_carries_no_value(dialect: Dialect, value: str) -> None:
    _, identity = _shape(Exposure.METADATA_ONLY, dialect)
    assert VALUES[value].lower() not in str(identity).lower()


@pytest.mark.parametrize("dialect", DIALECTS, ids=DIALECT_IDS)
def test_metadata_only_groups_as_masked_does(dialect: Dialect) -> None:
    """Two statements that differ only in a hidden value group under METADATA_ONLY exactly as under MASKED."""
    other = STATEMENT.replace(VALUES["key"], "otherplain9")

    def same_group(exposure: Exposure) -> bool:
        masker = Masker(exposure, True, OWN_TOKEN, identity_key=b"k" * 32)
        return (
            statement_shape(masker, STATEMENT, dialect).fingerprint
            == statement_shape(masker, other, dialect).fingerprint
        )

    assert same_group(Exposure.METADATA_ONLY) == same_group(Exposure.MASKED)


@pytest.fixture
def handles() -> Iterator[list[SharpitHandle]]:
    installed: list[SharpitHandle] = []
    yield installed
    for handle in installed:
        handle.uninstall_capture()


@pytest.mark.parametrize("path", ["sql-trace", "sql-trace/insights", "activity"])
@pytest.mark.parametrize("value", ["key", "token"])
def test_metadata_only_routes_show_no_code_position_value(handles: list[SharpitHandle], path: str, value: str) -> None:
    engine = sa.create_engine("sqlite://")
    app = FastAPI()
    # the bare words name no column, so SQLite fails the statement, and the trace still records its text
    sql = f"update u set note = 'x' where password = {VALUES['key']} and k = {VALUES['token']}"

    @app.get("/run")
    def run() -> dict[str, str]:
        with engine.connect() as conn:
            conn.exec_driver_sql("create table if not exists u (id int, note text)")
            with pytest.raises(sa.exc.OperationalError):
                conn.exec_driver_sql(sql)
        return {"ok": "1"}

    handles.append(install(app, enabled="ON", show_banner=False, engines=[engine], expose_values="METADATA_ONLY"))
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
    assert client.get("/run").status_code == 200
    response = client.get(f"/sharpit/api/{path}")
    assert response.status_code == 200
    assert VALUES[value] not in response.text
