from __future__ import annotations

from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install


def test_side_effects_rest_uses_the_service_when_a_ringed_sensor_is_configured(recorded_audit_hook: object) -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False, agent_sensors=("files",))
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        report = client.get("/sharpit/api/side-effects").json()
        page = client.get("/sharpit/api/side-effects/sensor?sensor=files").json()
    assert report["available"] is True
    assert next(item for item in report["sensors"] if item["id"] == "files")["state"] == "recording"
    assert page["available"] is True
    assert list(page) == ["available", "unavailableReason", "sensor", "rows", "page", "limitations"]
