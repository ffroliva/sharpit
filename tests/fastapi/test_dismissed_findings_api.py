"""``{api}/dismissed-findings`` (BootUI 2.2.0 ``DismissedFindingsController``): global read-only only, fixed errors."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.advisors.dismissals import FILE_NAME, MAX_FINDINGS
from sharpit.fastapi import adapter

LOCAL = ("127.0.0.1", 50000)
PATH = "/sharpit/api/dismissed-findings"
RULE = "RAPI-MAP-001"
IDENTITY = "v1:route=GET:/owners/{id}"
BODY = {"ruleId": RULE, "identity": IDENTITY, "note": "Intentional"}
CANARY = "canary-note-7f3a"
INVALID = "Request body must be a JSON object with string fields ruleId, identity and an optional note."
JSON = {"Content-Type": "application/json"}


def _client(state_dir: Path, **options: Any) -> TestClient:
    app = FastAPI()
    install(app, **{"enabled": "ON", "show_banner": False, "state_dir": str(state_dir), **options})
    return TestClient(app, base_url="http://localhost", client=LOCAL, follow_redirects=False)


def _send(client: TestClient, method: str, body: object, path: str = PATH, **headers: str) -> Any:
    raw = body if isinstance(body, str) else __import__("json").dumps(body)
    return client.request(method, path, content=raw.encode(), headers={**JSON, **headers})


# ported: DismissedFindingsControllerTests.mvcDismissesListsAndRestoresAFindingWithItsNote
def test_mvc_dismisses_lists_and_restores_a_finding_with_its_note(tmp_state_dir: Path):
    client = _client(tmp_state_dir)
    posted = _send(client, "POST", BODY)
    assert posted.status_code == 200
    assert posted.json() == {"dismissed": [{"ruleId": RULE, "identity": IDENTITY, "note": "Intentional"}], "ignored": 0}
    assert client.get(PATH).json() == posted.json()
    restored = _send(client, "DELETE", {"ruleId": RULE, "identity": IDENTITY})
    assert restored.json() == {"dismissed": [], "ignored": 0}


# ported: DismissedFindingsControllerTests.mvcRefusesBadBodiesWithAFixedMessageThatNeverQuotesTheNote
def test_mvc_refuses_bad_bodies_with_a_fixed_message_that_never_quotes_the_note(tmp_state_dir: Path):
    client = _client(tmp_state_dir)
    for body in (
        f'{{"note":"{CANARY}"}}',
        f'{{"ruleId":"{RULE}","identity":"bad identity","note":"{CANARY}"}}',
        f'{{"ruleId":"{RULE}","identity":"v1:a=b","note":7}}',
        f'["{CANARY}"]',
        f'{{"ruleId":"{RULE}","identity":["{CANARY}"]}}',
        f'{{"ruleId":"{RULE}", "identity": "{CANARY}',
        "",
    ):
        refused = _send(client, "POST", body)
        assert refused.status_code == 400
        assert isinstance(refused.json()["error"], str)
        assert CANARY not in refused.text
        if '"note":7' not in body:  # a restore reads no note, so only a bad rule id or identity can refuse it
            assert _send(client, "DELETE", body).status_code == 400
    assert _send(client, "POST", "{}").json() == {"error": INVALID}
    assert client.post(PATH, content=b"{}", headers={"Content-Type": "text/plain"}).status_code == 415
    assert client.get(PATH).json() == {"dismissed": [], "ignored": 0}


# ported: DismissedFindingsControllerTests.mvcGlobalReadOnlyBlocksTheMutationsButNotTheList
def test_mvc_global_read_only_blocks_the_mutations_but_not_the_list(tmp_state_dir: Path):
    client = _client(tmp_state_dir, read_only=True)
    denied = {
        "error": "sharpit panel access denied",
        "panel": "dismissed-findings",
        "reason": "sharpit is read-only via SHARPIT_READ_ONLY=true",
    }
    for method, path in (("POST", PATH), ("DELETE", PATH), ("POST", PATH + "/")):
        resp = _send(client, method, BODY, path)
        assert resp.status_code == 403
        assert resp.json() == denied
    assert client.get(PATH).status_code == 200
    assert not (tmp_state_dir / FILE_NAME).exists()


# ported: DismissedFindingsControllerTests.mvcReadsTheBodyAsBytesSoTheFrameworkNeverLogsTheNote
def test_mvc_reads_the_body_as_bytes_so_the_framework_never_logs_the_note(
    tmp_state_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    caps: list[int] = []
    real = adapter._read_capped  # pyright: ignore[reportPrivateUsage]

    async def recording(request: Any, cap: int) -> bytes | None:
        caps.append(cap)
        return await real(request, cap)

    monkeypatch.setattr(adapter, "_read_capped", recording)
    assert _send(_client(tmp_state_dir), "POST", BODY).status_code == 200
    assert caps == [65_536]


def test_dismissed_findings_requires_json_content_type_and_enforces_409_503(tmp_state_dir: Path):
    client = _client(tmp_state_dir)
    assert client.post(PATH, content=b"{}").status_code == 415  # no Content-Type at all
    charset = _send(client, "POST", BODY, **{"Content-Type": "application/json; charset=utf-8"})
    assert charset.status_code == 200
    too_big = _send(client, "POST", {**BODY, "note": "x" * 70_000})
    assert too_big.status_code == 413
    lines = "".join(f"  - {RULE} v1:m{i}\n" for i in range(MAX_FINDINGS))
    (tmp_state_dir / FILE_NAME).write_text(f"dismissedFindings:\n{lines}", encoding="utf-8")
    full = _send(client, "POST", {"ruleId": RULE, "identity": "v1:overflow"})
    assert full.status_code == 409
    assert full.json() == {"error": "Too many dismissed findings: restore some before dismissing more."}
    long_note = _send(client, "POST", {"ruleId": RULE, "identity": "v1:m1", "note": "x" * 201})
    assert long_note.json() == {"error": "Dismissed finding note must be at most 200 characters."}
    # sharpit: state_dir is always a path (default ".sharpit"), so BootUI's no-store 503 has no sharpit counterpart
