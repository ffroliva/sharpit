"""Each live server answers ``SELECT 1`` through SQLAlchemy: the job proves the fixture before a real test uses it."""

import pytest
from sqlalchemy import create_engine, text

from .conftest import SERVERS, LiveServer

pytestmark = [pytest.mark.live, pytest.mark.needs_sqlalchemy]


@pytest.mark.parametrize("server", list(SERVERS), indirect=True)
def test_a_server_answers(server: LiveServer) -> None:
    engine = create_engine(server.url)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
    finally:
        engine.dispose()
