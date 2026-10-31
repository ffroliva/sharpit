"""Shared ``{api}/dismissed-rules`` routes: global read-only plus the owning panel's gate (spec §8, §13.2)."""

from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.advisors.dismissals import FILE_NAME

LOCAL = ("127.0.0.1", 50000)
API = "/sharpit/api/dismissed-rules"
RAPI = "RAPI-MAP-001"
VULN = "V-1::pypi:widget"


def _client(state_dir: Path, **options: Any) -> TestClient:
    app = FastAPI()
    install(app, **{"enabled": "ON", "show_banner": False, "state_dir": str(state_dir), **options})
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False)


def _denied(reason: str) -> dict[str, str]:
    return {"error": "sharpit panel access denied", "panel": "dismissed-rules", "reason": reason}


def test_dismiss_and_restore_rest_api_rule(tmp_state_dir: Path):
    client = _client(tmp_state_dir)
    assert client.post(f"{API}/{RAPI}").json() == {"dismissed": [RAPI]}
    assert client.post(f"{API}/{quote(VULN, safe='')}").json() == {"dismissed": [RAPI, VULN]}
    assert client.get(API).json() == {"dismissed": [RAPI, VULN]}
    assert client.delete(f"{API}/{RAPI}").json() == {"dismissed": [VULN]}


@pytest.mark.parametrize("method", ["POST", "DELETE"])
def test_dismiss_rest_api_rule_refused_when_rest_api_read_only(tmp_state_dir: Path, method: str):
    client = _client(tmp_state_dir, panels={"rest-api": {"read_only": True}})
    resp = client.request(method, f"{API}/{RAPI}")
    assert (resp.status_code, resp.json()) == (
        403,
        _denied("Panel is read-only via SHARPIT_PANELS_REST_API_READ_ONLY=true"),
    )
    assert not (tmp_state_dir / FILE_NAME).exists()
    assert client.post(f"{API}/{quote(VULN, safe='')}").status_code == 200  # another panel's rule is unaffected
    assert client.get(API).status_code == 200  # listing is a read


@pytest.mark.parametrize("method", ["POST", "DELETE"])
def test_dismiss_vuln_refused_when_vulnerabilities_disabled(tmp_state_dir: Path, method: str):
    client = _client(tmp_state_dir, panels={"vulnerabilities": {"enabled": False}})
    resp = client.request(method, f"{API}/{quote(VULN, safe='')}")
    assert (resp.status_code, resp.json()) == (
        403,
        _denied("Panel is disabled via SHARPIT_PANELS_VULNERABILITIES_ENABLED=false"),
    )
    assert not (tmp_state_dir / FILE_NAME).exists()
    assert client.post(f"{API}/{RAPI}").json() == {"dismissed": [RAPI]}  # a REST API rule still works


def test_dismiss_rest_api_rule_refused_when_rest_api_disabled(tmp_state_dir: Path):
    client = _client(tmp_state_dir, panels={"rest-api": {"enabled": False}})
    resp = client.post(f"{API}/{RAPI}")
    assert (resp.status_code, resp.json()) == (
        403,
        _denied("Panel is disabled via SHARPIT_PANELS_REST_API_ENABLED=false"),
    )


@pytest.mark.parametrize("rule", ["SPRING-WEB-001", "V-1::widget", "V-1::pypi:Widget", "rapi-map-001"])
def test_unknown_owner_400(tmp_state_dir: Path, rule: str):
    client = _client(tmp_state_dir)
    for method in ("POST", "DELETE"):
        resp = client.request(method, f"{API}/{quote(rule, safe='')}")
        assert resp.status_code == 400, (method, rule)
        assert "error" in resp.json()
    assert not (tmp_state_dir / FILE_NAME).exists()


def test_global_read_only_checked_before_owner(tmp_state_dir: Path):
    client = _client(tmp_state_dir, read_only=True)
    for rule in (RAPI, "SPRING-WEB-001"):
        resp = client.post(f"{API}/{rule}")
        assert (resp.status_code, resp.json()) == (403, _denied("sharpit is read-only via SHARPIT_READ_ONLY=true"))
