"""Lane D1 safety rows (C5: kept out of tests/test_safety_matrix.py): ``{api}/dismissed-findings``."""

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from conftest import SideEffectGuard
from fastapi import FastAPI
from sharpit import install

PATH = "/sharpit/api/dismissed-findings"
STORED = "dismissedFindings:\n  - RAPI-MAP-001 v1:x\n"


def _client(state_dir: Path, **options: Any) -> TestClient:
    app = FastAPI()
    install(app, **{"enabled": "ON", "show_banner": False, "state_dir": str(state_dir), **options})
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000), follow_redirects=False)


def test_get_dismissed_findings_has_no_side_effects(no_side_effects: SideEffectGuard):
    (no_side_effects.state_dir / "sharpit.yml").write_text(STORED, "utf-8")
    no_side_effects.rebaseline()
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    with _client(no_side_effects.state_dir) as client:
        no_side_effects.block_network()
        resp = client.get(PATH)
    assert resp.status_code == 200
    assert resp.json() == {"dismissed": [{"ruleId": "RAPI-MAP-001", "identity": "v1:x", "note": None}], "ignored": 0}
    assert no_side_effects.violations == []


def test_get_dismissed_findings_is_allowed_with_every_advisor_panel_off(tmp_state_dir: Path):
    off = {"enabled": False}
    panels = {"rest-api": off, "vulnerabilities": off}
    resp = _client(tmp_state_dir, read_only=True, panels=panels).get(PATH)
    assert resp.status_code == 200


def test_dismissed_findings_keep_the_guard_floor(tmp_state_dir: Path):
    client = _client(tmp_state_dir)
    body = b'{"ruleId":"RAPI-MAP-001","identity":"v1:x"}'
    cross_site = {"Content-Type": "application/json", "Origin": "http://evil.example"}
    assert client.post(PATH, content=body, headers=cross_site).status_code == 403
    assert client.get(PATH, headers={"Host": "attacker.example"}).status_code == 403
    remote = TestClient(client.app, base_url="http://localhost", client=("203.0.113.9", 50000))
    assert remote.get(PATH).status_code == 403
    assert not (tmp_state_dir / "sharpit.yml").exists()


def test_inactive_sharpit_hides_dismissed_findings(tmp_state_dir: Path):
    resp = _client(tmp_state_dir, enabled="OFF").get(PATH)
    assert resp.status_code == 404
