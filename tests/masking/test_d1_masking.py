"""Lane D1 masking rows (C5: kept out of tests/test_masking_corpus.py): a dismissal note is user text that is never
echoed by an error and never leaves through MCP or the CLI (BootUI: no MCP or CLI binding for dismissed findings)."""

import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine import tools

PATH = "/sharpit/api/dismissed-findings"
SECRET = "password=hunter2-0xD1"
JSON = {"Content-Type": "application/json"}


def _client(state_dir: Path) -> TestClient:
    app = FastAPI()
    install(app, enabled="ON", show_banner=False, state_dir=str(state_dir))
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000), follow_redirects=False)


def test_a_secret_note_is_never_echoed_by_an_error(tmp_state_dir: Path):
    client = _client(tmp_state_dir)
    bodies: list[dict[str, Any]] = [
        {"ruleId": "RAPI-MAP-001", "identity": "v1:x", "note": SECRET * 20},  # too long
        {"ruleId": "RAPI-MAP-001", "identity": f"{SECRET} x", "note": SECRET},  # bad identity
        {"ruleId": SECRET, "identity": "v1:x", "note": SECRET},  # bad rule id
        {"ruleId": "RAPI-MAP-001", "identity": "v1:x", "note": [SECRET]},  # wrong type
    ]
    for body in bodies:
        resp = client.post(PATH, content=json.dumps(body).encode(), headers=JSON)
        assert resp.status_code == 400
        assert "hunter2" not in resp.text


def test_dismissed_findings_have_no_mcp_tool_or_cli_command():
    names = {tool.name for tool in tools.TOOLS}
    assert not {name for name in names if "dismiss" in name}
