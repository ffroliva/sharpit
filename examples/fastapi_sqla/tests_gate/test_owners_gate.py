"""One planted N+1 (red) and its fix (green): what `pytest --sharpit` gates on in CI.

CI runs the `fixed` test and requires it to pass, then runs the `n_plus_one` test and requires it to fail.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_owners_list_n_plus_one(client: TestClient) -> None:
    assert client.get("/owners/n-plus-one").status_code == 200


def test_owners_list_fixed(client: TestClient) -> None:
    assert client.get("/owners").status_code == 200
