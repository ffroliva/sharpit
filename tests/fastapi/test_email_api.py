"""Email panel routes, tool and CLI command (W7 lane E): BootUI ``EmailController`` and ``get_emails``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from conftest import SideEffectGuard
from mailsink import API, Harness, harness
from sharpit.engine.panels import PANELS

GOLDEN = Path(__file__).parents[1] / "fixtures/bootui/2.3.0/email/captured.json"
REPORT_KEYS = ["available", "unavailableReason", "devTrapEnabled", "maxEntries", "total", "messages"]
MESSAGE_KEYS = [
    "id", "timestamp", "from", "to", "cc", "bcc", "subject", "textBody", "htmlBody", "attachments", "sent",
    "traceId", "thread", "requestId",
]  # fmt: skip


def _mcp(h: Harness, tool: str) -> dict[str, Any]:
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": {}}}
    return h.client.post(f"{API}/mcp", json=call).json().get("result", {})


def test_email_panel_is_registered_and_implemented():
    from sharpit.engine.panels import panel_for_api_path

    with harness() as h:
        panels = {p["id"]: p for p in h.client.get(f"{API}/panels").json()["panels"]}
        assert "email" in panels  # finding W7-E r2 #5: the defect named before indexing
        assert panels["email"]["title"] == "Email"
        assert panel_for_api_path("/email").action_capable is True


def test_list_has_every_report_key_in_bootui_order():
    # ported: EmailControllerTests.listsCapturedEmailsWhenMailSenderIsPresent
    with harness() as h:
        h.send(subject="listed")
        report = h.client.get(f"{API}/email").json()
        assert list(report) == REPORT_KEYS
        assert report["available"] is True
        assert report["unavailableReason"] is None
        assert list(report["messages"][0]) == MESSAGE_KEYS


def test_empty_list_answers_the_golden_shape():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    with harness() as h:
        report = h.client.get(f"{API}/email").json()
        assert list(report) == list(golden)
        assert report["total"] == 0
        assert report["messages"] == []
        assert report["maxEntries"] == golden["maxEntries"]


def test_detail_answers_one_message():
    with harness() as h:
        h.send(subject="detail")
        assert h.emails()["total"] == 1  # finding W7-E r2 #5
        listed = h.client.get(f"{API}/email").json()["messages"][0]
        detail = h.client.get(f"{API}/email/{listed['id']}")
        assert detail.status_code == 200
        assert detail.json() == listed


def test_unknown_id_is_a_404():
    # ported: EmailControllerTests.returns404ForUnknownId
    with harness() as h:
        for path in ("/email/email-99", "/email/email-99/eml"):
            response = h.client.get(f"{API}{path}")
            assert response.status_code == 404
            assert response.json()["error"] == "email email-99 not found"


def test_eml_download_is_rfc822_built_from_the_stored_message():
    # ported: EmailControllerTests.downloadsEmlFile
    with harness() as h:
        h.send(subject="Download me", body="eml body", to=("dl@example.test",), attachment=b"%PDF-1")
        assert h.emails()["total"] == 1  # finding W7-E r2 #5
        message_id = h.client.get(f"{API}/email").json()["messages"][0]["id"]
        response = h.client.get(f"{API}/email/{message_id}/eml")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("message/rfc822")
        assert response.headers["content-disposition"] == f'attachment; filename="email-{message_id}.eml"'
        text = response.content.decode("utf-8")
        assert text.startswith("From: app@example.test\r\nTo: dl@example.test\r\nSubject: Download me\r\nDate: ")
        assert "Content-Type: text/plain; charset=UTF-8\r\n\r\neml body" in text
        assert "invoice.pdf (application/pdf, 6 bytes)" in text


def test_clear_removes_every_captured_email():
    # ported: EmailControllerTests.clearRemovesAllCapturedEmails
    with harness() as h:
        h.send()
        h.send()
        response = h.client.delete(f"{API}/email")
        assert response.status_code == 204
        assert h.emails()["total"] == 0


def _email_panel_exists() -> bool:
    """Finding W7-E r2 #5: asserted before ``harness(panels={"email": ...})``, which the settings refuse without it."""
    return "email" in {p.id for p in PANELS}


def test_clear_is_refused_when_the_panel_is_read_only():
    assert _email_panel_exists()
    with harness(panels={"email": {"read_only": True}}) as h:
        h.send()
        response = h.client.delete(f"{API}/email")
        assert response.status_code == 403
        assert response.json()["reason"] == "Panel is read-only via SHARPIT_PANELS_EMAIL_READ_ONLY=true"
        assert h.emails()["total"] == 1  # the handler did not run


def test_clear_is_refused_when_sharpit_is_read_only():
    with harness(read_only=True) as h:
        h.send()
        response = h.client.delete(f"{API}/email")
        assert response.status_code == 403
        assert response.json()["reason"] == "sharpit is read-only via SHARPIT_READ_ONLY=true"
        assert h.emails()["total"] == 1


def test_a_read_only_panel_still_answers_reads():
    assert _email_panel_exists()
    with harness(panels={"email": {"read_only": True}}) as h:
        h.send()
        assert h.emails()["total"] == 1


def test_clear_is_refused_when_the_panel_is_disabled():
    assert _email_panel_exists()
    with harness(panels={"email": {"enabled": False}}) as h:
        response = h.client.delete(f"{API}/email")
        assert response.status_code == 403
        assert response.json()["reason"] == "Panel is disabled via SHARPIT_PANELS_EMAIL_ENABLED=false"


def test_clear_from_an_untrusted_source_is_refused():
    with harness() as h:
        h.send()
        response = h.client.delete(f"{API}/email", headers={"host": "evil.example"})
        assert response.status_code in (403, 421)
        assert h.emails()["total"] == 1


def test_reads_have_no_side_effects(no_side_effects: SideEffectGuard):
    no_side_effects.unblock_network()  # TestClient's Windows Proactor loop connects a self-pipe socketpair once
    with harness() as h, h.client as client:
        recorder = getattr(h.handle.context.capture, "mail", None)
        assert recorder is not None
        recorder.record("a@example.test", ["b@example.test"], "Subject: quiet\n\nbody\n")  # no socket
        client.get(f"{API}/panels")
        no_side_effects.block_network()
        for path in ("/email", "/email/email-1", "/email/email-1/eml"):  # finding W7-E r2 #5: never a 404 sweep
            assert client.get(f"{API}{path}").status_code == 200


def test_get_emails_tool_answers_the_report_over_mcp():
    with harness(mcp_enabled="ON") as h:
        h.send(subject="over mcp")
        result = _mcp(h, "get_emails")
        assert result.get("isError") is False
        assert result["structuredContent"]["messages"][0]["subject"] == "over mcp"


def test_get_emails_tool_masks_secrets():
    secret = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    with harness(mcp_enabled="ON") as h:
        h.send(subject="s", body=f"token {secret}")
        report = _mcp(h, "get_emails")
        assert report.get("isError") is False  # finding W7-E r2 #5
        assert report["structuredContent"]["total"] == 1
        assert secret not in json.dumps(report)


def test_mail_cli_command_runs_the_tool():
    with harness() as h:
        h.send(subject="over cli")
        response = h.client.post(f"{API}/cli/tools/get_emails", json={})
        assert response.status_code == 200
        assert response.json()["messages"][0]["subject"] == "over cli"


def test_the_secret_scrub_is_described_as_it_behaves():
    # finding W7-E r2 #4: under FULL a body within the limit shows the secret, so no text may say it is always masked
    secret = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    with harness(expose_values="FULL") as h:
        h.send(body=f"token {secret}")
        report = h.emails()
        assert report["total"] == 1
        assert secret in report["messages"][0]["textBody"]
    from sharpit.engine.tools04.email import TOOLS

    assert "always" not in TOOLS[0].description
    root = Path(__file__).parents[2]
    lines = [
        *(x for x in (root / "website/docs/mcp.md").read_text(encoding="utf-8").splitlines() if "`get_emails`:" in x),
        *(x for x in (root / "skills/sharpit/SKILL.md").read_text(encoding="utf-8").splitlines() if "| Email |" in x),
    ]
    assert len(lines) == 2
    for line in lines:
        assert "always" not in line
