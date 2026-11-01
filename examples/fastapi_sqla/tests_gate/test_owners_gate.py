"""One planted N+1 (red) and its fix (green): what `pytest --sharpit` gates on in CI.

CI runs the `fixed` test and requires it to pass, then runs the `n_plus_one` test and requires it to fail.
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import text


def _touch_async_engine(client: TestClient) -> None:
    """Run one query on the app's aiosqlite engine so sharpit sees it and the run can end `pass`, not `unknown`."""

    async def ping() -> None:
        async with client.app.state.async_engine.connect() as conn:  # type: ignore[attr-defined]
            await conn.execute(text("SELECT 1"))

    asyncio.run(ping())


def test_owners_list_n_plus_one(client: TestClient) -> None:
    assert client.get("/owners/n-plus-one").status_code == 200


def test_owners_list_fixed(client: TestClient) -> None:
    assert client.get("/owners").status_code == 200
    _touch_async_engine(client)
