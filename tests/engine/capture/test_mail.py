"""Outgoing mail capture (W7 lane E): delivery is never affected, ``sendmail`` is the one wrap point, bodies are bound
at capture, secrets never reach an output, and the journal event holds metadata only."""

from __future__ import annotations

import asyncio
import smtplib
import sys
import types
from email.message import EmailMessage
from typing import Any

import pytest

from mailsink import API, harness

SECRET = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
RESET = "https://app.example.test/reset?token=" + "r3s3t" + "9x8y7z6w5v4u"
PASSWORD = "password=" + "hunter2" + "xyz"


def _plain_sendmail() -> Any:
    return smtplib.SMTP.__dict__["sendmail"]


def test_send_message_is_delivered_and_captured_once():
    # ported: CapturingJavaMailSenderTests.passesMimeMessageThroughAndCapturesIt
    with harness() as h:
        h.send(subject="Welcome", body="hello there", to=("bob@example.test",))
        report = h.emails()
        assert len(h.sink.messages) == 1
        assert report["total"] == 1
        message = report["messages"][0]
        assert message["subject"] == "Welcome"
        assert message["to"] == ["bob@example.test"]
        assert message["from"] == "app@example.test"
        assert message["sent"] is True


def test_sendmail_with_a_raw_string_is_captured():
    with harness() as h:
        h.sendmail("From: a@example.test\r\nTo: b@example.test\r\nSubject: raw\r\n\r\nraw body\r\n")
        message = h.emails()["messages"][0]
        assert message["subject"] == "raw"
        assert message["textBody"].strip() == "raw body"
        assert len(h.sink.messages) == 1


def test_multipart_message_keeps_both_bodies_and_attachment_metadata_only():
    # ported: MimeMessageInspectorTests.parsesMultipartMessageWithHtmlBodyAndAttachment
    with harness() as h:
        h.send(body="the text", html="<p>the html</p>", attachment=b"%PDF-" + b"x" * 100)
        message = h.emails()["messages"][0]
        assert message["textBody"].strip() == "the text"
        assert message["htmlBody"].strip() == "<p>the html</p>"
        assert message["attachments"] == [
            {"filename": "invoice.pdf", "contentType": "application/pdf", "sizeBytes": 105}
        ]


def test_plain_message_has_no_html_and_no_attachments():
    # ported: MimeMessageInspectorTests.parsesSimplePlainTextMessage
    with harness() as h:
        h.send(body="just text", cc=("carol@example.test",))
        message = h.emails()["messages"][0]
        assert message["htmlBody"] is None
        assert message["attachments"] == []
        assert message["cc"] == ["carol@example.test"]


def test_bcc_recipients_come_from_the_envelope():
    with harness() as h:
        h.send(to=("a@example.test",), bcc=("hidden@example.test",))
        message = h.emails()["messages"][0]
        assert message["bcc"] == ["hidden@example.test"]
        assert message["to"] == ["a@example.test"]


def test_messages_are_listed_newest_first():
    # ported: EmailStoreTests.capturesNewestFirst
    with harness() as h:
        h.send(subject="first")
        h.send(subject="second")
        assert [m["subject"] for m in h.emails()["messages"]] == ["second", "first"]


def test_oldest_message_is_evicted_once_full():
    # ported: EmailStoreTests.evictsOldestOnceFull
    with harness(email_max_entries=2) as h:
        for subject in ("one", "two", "three"):
            h.send(subject=subject)
        report = h.emails()
        assert report["maxEntries"] == 2
        assert [m["subject"] for m in report["messages"]] == ["three", "two"]
        assert report["total"] == 2


def test_oversized_body_is_cut_at_the_configured_limit():
    # ported: EmailStoreTests.truncatesOversizedBodiesAtConfiguredLimit
    with harness(email_max_body_length=50) as h:
        h.send(body="y" * 200)
        body = h.emails()["messages"][0]["textBody"]
        assert body.startswith("y" * 50)
        assert body.endswith("[truncated, showing 50 of 201 characters]")  # the sender adds the final newline


def test_body_within_the_limit_is_unchanged():
    # ported: EmailStoreTests.leavesBodiesUnchangedWhenWithinLimit
    with harness(email_max_body_length=50) as h:
        h.send(body="short")
        assert h.emails()["messages"][0]["textBody"].strip() == "short"


def test_cutting_a_body_never_stores_a_fragment_of_a_secret():
    with harness(email_max_body_length=100, expose_values="FULL") as h:
        h.send(body="z" * 90 + " " + SECRET)
        body = h.emails()["messages"][0]["textBody"]
        assert SECRET[:8] not in body
        assert SECRET[4:20] not in body


def test_pass_through_still_sends_and_flags_sent():
    # ported: EmailCaptureServiceTests.passThroughModeStillSends
    with harness() as h:
        h.send()
        assert len(h.sink.messages) == 1
        assert h.emails()["messages"][0]["sent"] is True
        assert h.emails()["devTrapEnabled"] is False


def test_dev_trap_captures_and_suppresses_the_real_send():
    # ported: CapturingJavaMailSenderTests.devTrapModeSuppressesRealSend
    # ported: EmailCaptureServiceTests.devTrapModeSuppressesRealSend
    with harness(email_dev_trap=True) as h:
        h.send(subject="trapped")
        report = h.emails()
        assert h.sink.messages == []
        assert report["devTrapEnabled"] is True
        assert report["messages"][0]["subject"] == "trapped"
        assert report["messages"][0]["sent"] is False


def test_email_capture_runs_with_panel_disabled():
    with harness(panels={"email": {"enabled": False}}, email_dev_trap=True) as h:
        h.send(subject="still captured")
        records = h.mail_records()
        assert len(records) == 1
        assert h.sink.messages == []  # the dev trap works with the panel off, as BootUI's capture does
        assert h.client.get(f"{API}/email").status_code == 403


def test_capture_raising_never_affects_delivery(monkeypatch: pytest.MonkeyPatch):
    from sharpit.engine.capture import mail

    def boom(*_args: Any, **_kwargs: Any) -> bool:  # noqa: ARG001
        raise RuntimeError("capture exploded")

    with harness() as h:
        real = mail.MailRecorder.record
        monkeypatch.setattr(mail.MailRecorder, "record", boom)
        h.send(subject="lost to the capture")
        assert len(h.sink.messages) == 1
        monkeypatch.setattr(mail.MailRecorder, "record", real)
        h.send(subject="captured again")
        assert [m["subject"] for m in h.emails()["messages"]] == ["captured again"]
        assert len(h.sink.messages) == 2


def test_mail_hook_is_registered_and_a_paused_hook_delivers_without_capturing():
    with harness() as h:
        hook = h.hook("mail")
        assert hook is not None
        hook.suspend()
        h.send(subject="while paused")
        assert len(h.sink.messages) == 1
        assert h.emails()["total"] == 0
        hook.resume()
        h.send(subject="after resume")
        assert [m["subject"] for m in h.emails()["messages"]] == ["after resume"]


def test_low_footprint_discard_drops_what_is_retained():
    with harness() as h:
        h.send()
        h.handle.context.capture.hooks.discard()
        assert h.emails()["total"] == 0


def test_uninstall_restores_smtplib_and_later_mail_is_not_captured():
    original = _plain_sendmail()
    with harness() as h:
        assert hasattr(_plain_sendmail(), "__sharpit_original__")
        h.handle.uninstall_capture()
        assert _plain_sendmail() is original
        h.send()
        assert len(h.sink.messages) == 1
        assert h.emails()["total"] == 0


def test_two_installs_each_capture_and_the_last_one_out_restores_smtplib():
    original = _plain_sendmail()
    with harness() as first, harness() as second:
        second.sendmail("Subject: shared\r\n\r\nbody\r\n")
        assert first.emails()["total"] == 1  # the wrap is process-wide: every armed context records the call
        assert second.emails()["total"] == 1
        first.handle.uninstall_capture()
        second.sendmail("Subject: again\r\n\r\nbody\r\n")
        assert first.emails()["total"] == 1
        assert second.emails()["total"] == 2
    assert _plain_sendmail() is original


@pytest.fixture
def fake_aiosmtplib(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    module = types.ModuleType("aiosmtplib")

    class SMTP:
        sent: list[tuple[str, Any, Any]] = []  # noqa: RUF012

        async def sendmail(
            self, sender: str, recipients: Any, message: Any, **_options: Any
        ) -> tuple[dict[str, Any], str]:
            self.sent.append((sender, recipients, message))
            return {}, "OK"

        async def send_message(self, message: Any) -> tuple[dict[str, Any], str]:
            return await self.sendmail(message["From"], [message["To"]], message.as_bytes())

    module.SMTP = SMTP  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "aiosmtplib", module)
    return module


def _message() -> EmailMessage:
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = "app@example.test", "z@example.test", "async hello"
    message.set_content("async body")
    return message


def test_aiosmtplib_send_message_is_captured_once_and_delivered(fake_aiosmtplib: types.ModuleType):
    with harness() as h:
        smtp = fake_aiosmtplib.SMTP()  # type: ignore[attr-defined]
        result = asyncio.run(smtp.send_message(_message()))
        assert result == ({}, "OK")
        assert len(smtp.sent) == 1
        assert [m["subject"] for m in h.emails()["messages"]] == ["async hello"]


def test_aiosmtplib_dev_trap_answers_the_library_shape_without_sending(fake_aiosmtplib: types.ModuleType):
    with harness(email_dev_trap=True) as h:
        smtp = fake_aiosmtplib.SMTP()  # type: ignore[attr-defined]
        result = asyncio.run(smtp.send_message(_message()))
        assert result == ({}, "OK")
        assert smtp.sent == []
        assert h.emails()["messages"][0]["sent"] is False


def test_mail_journal_event_is_metadata_only():
    # ported: EmailCaptureServiceTests.publishesOnlyTheEmailsMetadataToTheRuntimeJournal
    with harness() as h:
        h.send(subject="subject canary 8c1f", body="body canary 8c1f", to=("who@example.test",), attachment=b"%PDF-1")
        records = h.mail_records()
        assert len(records) == 1
        record = records[0]
        assert record["source"] == "mail"
        assert record["recipients"] == 1
        assert record["attachments"] == 1
        assert record["sent"] is True
        assert record["failed"] is False
        assert set(record) == {
            "source", "recipients", "attachments", "sent", "failed", "traceId", "requestId", "thread",
            "durationNanos", "completedNanos", "codePathStamp",
        }  # fmt: skip
        text = repr(record)
        for canary in ("canary", "who@example.test", "app@example.test", "invoice.pdf"):
            assert canary not in text


def test_trapped_mail_is_a_failed_journal_event():
    with harness(email_dev_trap=True) as h:
        h.send()
        record = h.mail_records()[0]
        assert record["sent"] is False
        assert record["failed"] is True


def test_journal_source_off_records_no_mail_event():
    with harness(runtime_journal_sources="http") as h:
        h.send()
        assert h.mail_records() == ()
        assert h.emails()["total"] == 1


@pytest.mark.parametrize("exposure", ["MASKED", "FULL"])
def test_the_console_token_never_reaches_an_output(exposure: str):
    with harness(expose_values=exposure) as h:
        token = h.handle.context.token
        assert token
        h.send(
            subject=f"hi {token}", body=f"link {token}", sender=f"{token}@example.test", to=(f"{token}@example.test",)
        )
        for path in ("", "/email-1", "/email-1/eml"):
            response = h.client.get(f"{API}/email{path}")
            assert response.status_code == 200
            assert token not in response.text


@pytest.mark.parametrize("secret", [SECRET, RESET, PASSWORD])
def test_a_secret_in_any_field_never_reaches_an_output_at_masked(secret: str):
    with harness() as h:  # mask-content is off: BootUI reveals content, sharpit's scrub still hides secrets
        h.send(subject=f"s {secret}", body=f"b {secret}", html=f"<p>{secret}</p>", sender="x@example.test")
        for path in ("", "/email-1", "/email-1/eml"):
            response = h.client.get(f"{API}/email{path}")
            assert response.status_code == 200
            assert secret not in response.text
            assert secret[-10:] not in response.text


def test_ordinary_content_is_revealed_by_default():
    # ported: EmailCaptureServiceTests.revealsFieldsByDefaultEvenWhenValueExposureIsMasked
    with harness() as h:
        h.send(subject="Your invoice", body="Thanks for your order", to=("alice@example.test",))
        message = h.emails()["messages"][0]
        assert message["subject"] == "Your invoice"
        assert message["to"] == ["alice@example.test"]
        assert message["textBody"].strip() == "Thanks for your order"


def test_mask_content_masks_every_field_unless_full():
    # ported: EmailCaptureServiceTests.masksSensitiveFieldsWhenMaskContentEnabled
    with harness(email_mask_content=True) as h:
        h.send(subject="Secret plans", body="body", to=("alice@example.test",), bcc=("b@example.test",))
        message = h.emails()["messages"][0]
        assert message["subject"] == "******"
        assert message["from"] == "******"
        assert message["to"] == ["******"]
        assert message["bcc"] == ["******"]
        assert message["textBody"] == "******"
        assert message["htmlBody"] is None


def test_mask_content_is_lifted_by_full_exposure():
    # ported: EmailCaptureServiceTests.revealsFieldsUnderFullExposureEvenWhenMaskContentEnabled
    with harness(email_mask_content=True, expose_values="FULL") as h:
        h.send(subject="Visible plans")
        assert h.emails()["messages"][0]["subject"] == "Visible plans"


def test_the_exposed_flags_report_the_settings():
    # ported: EmailCaptureServiceTests.exposesMaskContentFlag
    with harness(email_mask_content=True, email_dev_trap=True, email_max_entries=7) as h:
        report = h.emails()
        assert report["devTrapEnabled"] is True
        assert report["maxEntries"] == 7
