"""Safety sweep for the read-only base-panel error-contract route."""

from fastapi.testclient import TestClient

from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install


def test_error_contract_get_has_no_side_effects(no_side_effects: SideEffectGuard) -> None:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, config_scan=False, state_dir=str(no_side_effects.state_dir))
    no_side_effects.unblock_network()
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
        no_side_effects.block_network()
        response = client.get("/sharpit/api/rest-api/error-contract")
    assert response.status_code == 200
    assert no_side_effects.violations == []
