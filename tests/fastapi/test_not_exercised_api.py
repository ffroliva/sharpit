"""Declared route exercise coverage over real HTTP capture."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sharpit import install

API = "/sharpit/api/runtime-insights"


def test_a_route_nobody_called_is_listed_and_a_called_one_is_not():
    app = FastAPI()

    @app.get("/called/{item_id}")
    @app.get("/uncalled")
    def endpoint(item_id: str = ""):
        return item_id

    install(app, enabled="ON", show_banner=False, config_scan=False)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        assert client.get("/called/7").status_code == 200
        assert client.get(API).json()["notExercised"] == ["GET /uncalled"]
