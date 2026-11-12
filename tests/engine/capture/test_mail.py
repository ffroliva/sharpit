"""Outgoing mail capture (W7 lane E): delivery is never affected, ``sendmail`` is the one wrap point, bodies are bound
at capture, secrets never reach an output, and the journal event holds metadata only."""

from __future__ import annotations

import asyncio
import gc
import smtplib
import socket
import sys
import threading
import types
import weakref
from collections.abc import Callable
from email.message import EmailMessage
from typing import Any, ClassVar, NamedTuple

import pytest

from fastapi import FastAPI, WebSocket
from mailsink import API, OPTIONS, Harness, harness, smtp_sink
from sharpit import install
from sharpit.engine.panels import PANELS

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
    assert "email" in {p.id for p in PANELS}  # finding W7-E r2 #5: the defect named before the settings refuse it
    with harness(panels={"email": {"enabled": False}}, email_dev_trap=True) as h:
        h.send(subject="still captured")
        records = h.mail_records()
        assert len(records) == 1
        assert h.sink.messages == []  # the dev trap works with the panel off, as BootUI's capture does
        assert h.client.get(f"{API}/email").status_code == 403


def _boom(*_args: Any, **_kwargs: Any) -> None:
    raise RuntimeError("capture exploded")


def test_capture_raising_never_affects_delivery(monkeypatch: pytest.MonkeyPatch):
    from sharpit.engine.capture import mail

    with harness() as h:
        real = mail.parse
        monkeypatch.setattr(mail, "parse", _boom)
        h.send(subject="lost to the capture")
        assert len(h.sink.messages) == 1
        monkeypatch.setattr(mail, "parse", real)
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


class _Response(NamedTuple):  # aiosmtplib.SMTPResponse
    code: int
    message: str


class _AsyncSMTP:
    """aiosmtplib's shape (5.1.3, smtp.py): ``connect`` opens the transport in ``_create_connection``, and every
    command after it (login, quit) runs through ``self.protocol``; no server is reachable here."""

    attempts: ClassVar[list[object]] = []

    def __init__(self) -> None:
        self.sent: list[tuple[str, Any, Any]] = []
        self.protocol: Any = None

    async def _create_connection(self, timeout: float | None) -> _Response:
        self.attempts.append(timeout)
        raise ConnectionRefusedError("no SMTP server reachable")

    async def connect(self) -> _Response:
        return await self._create_connection(timeout=None)

    async def execute_command(self, *args: bytes, timeout: float | None = None) -> _Response:
        if self.protocol is None:
            raise ConnectionError("Server not connected")
        return await self.protocol.execute_command(*args, timeout=timeout)

    async def login(self, username: str, password: str) -> _Response:
        response = await self.execute_command(b"AUTH", b"PLAIN", f"{username}:{password}".encode())
        assert response.code == 235
        return response

    async def quit(self) -> _Response:
        response = await self.execute_command(b"QUIT")
        self.protocol = None
        return response

    async def __aenter__(self) -> _AsyncSMTP:
        await self.connect()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.quit()

    async def sendmail(self, sender: str, recipients: Any, message: Any, **_options: Any) -> tuple[dict[str, Any], str]:
        self.sent.append((sender, recipients, message))
        return {}, "OK"

    async def send_message(self, message: Any) -> tuple[dict[str, Any], str]:
        return await self.sendmail(message["From"], [message["To"]], message.as_bytes())


@pytest.fixture
def fake_aiosmtplib(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    module = types.ModuleType("aiosmtplib")
    monkeypatch.setattr(_AsyncSMTP, "attempts", [])
    module.SMTP = _AsyncSMTP  # type: ignore[attr-defined]
    module.SMTPResponse = _Response  # type: ignore[attr-defined]
    module.attempts = _AsyncSMTP.attempts  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "aiosmtplib", module)
    return module


def _message(subject: str = "async hello") -> EmailMessage:
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = "app@example.test", "z@example.test", subject
    message.set_content("async body")
    return message


@pytest.fixture
def no_smtp_server(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Every SMTP connection attempt (``smtplib`` opens its socket with ``socket.create_connection``), refused as if
    no server were reachable."""
    attempts: list[object] = []

    def refuse(address: object, *_args: Any, **_kwargs: Any) -> socket.socket:
        attempts.append(address)
        raise ConnectionRefusedError("no SMTP server reachable")

    monkeypatch.setattr(socket, "create_connection", refuse)
    return attempts


def _host_session(subject: str) -> object:
    """A host's usual ``smtplib`` session: connect, STARTTLS, login, send, quit; its answer, or what it raised."""
    try:
        with smtplib.SMTP("smtp.example.test", 587, local_hostname="app.example.test") as smtp:
            smtp.starttls()
            smtp.login("app", "app-" + "password")
            return smtp.send_message(_message(subject))
    except OSError as exc:  # smtplib.SMTPException is an OSError
        return exc


def test_dev_trap_never_connects_and_the_host_sees_success(no_smtp_server: list[object]):
    # finding W7-E r2 #2: BootUI's trap skips the transport; sharpit's ran EHLO, STARTTLS and AUTH before sendmail
    with harness(email_dev_trap=True) as h:
        answer = _host_session("trapped offline")
        assert no_smtp_server == []
        assert answer == {}
        report = h.emails()
        assert [m["subject"] for m in report["messages"]] == ["trapped offline"]
        assert report["messages"][0]["sent"] is False


def test_aiosmtplib_dev_trap_never_connects(fake_aiosmtplib: types.ModuleType):
    # finding W7-E r2 #2: aiosmtplib connected and logged in before sendmail
    async def session() -> object:
        try:
            async with fake_aiosmtplib.SMTP() as smtp:  # type: ignore[attr-defined]
                await smtp.login("app", "app-" + "password")
                return await smtp.send_message(_message("async trapped"))
        except OSError as exc:
            return exc

    with harness(email_dev_trap=True) as h:
        answer = asyncio.run(session())
        assert fake_aiosmtplib.attempts == []  # type: ignore[attr-defined]
        assert answer == ({}, "OK")
        assert [m["subject"] for m in h.emails()["messages"]] == ["async trapped"]


def test_without_the_trap_a_session_connects_as_it_would_without_sharpit(no_smtp_server: list[object]):
    with harness() as h:
        answer = _host_session("offline")
        assert no_smtp_server == [("smtp.example.test", 587)]
        assert isinstance(answer, ConnectionRefusedError)
        assert h.emails()["total"] == 0


def test_a_capture_failure_under_the_trap_still_sends_a_connected_session(monkeypatch: pytest.MonkeyPatch):
    # finding W7-E r2 #3: BootUI's captureMime answers true when it cannot capture, so the message is sent
    from sharpit.engine.capture import mail

    with smtp_sink() as sink:
        smtp = smtplib.SMTP("127.0.0.1", sink.port)  # connected before the trap armed: a real session
        h = Harness(sink, email_dev_trap=True)
        try:
            monkeypatch.setattr(mail, "parse", _boom)
            answer = smtp.sendmail("app@example.test", ["b@example.test"], "Subject: kept\r\n\r\nbody\r\n")
            smtp.quit()
        finally:
            h.handle.uninstall_capture()
        assert answer == {}
        assert len(sink.messages) == 1


def test_a_capture_failure_on_a_trapped_session_is_not_sent(
    no_smtp_server: list[object], monkeypatch: pytest.MonkeyPatch
):
    # proposed deviation D-E2: a trapped session never connected, so a failed capture has no transport to fall back to
    from sharpit.engine.capture import mail

    with harness(email_dev_trap=True) as h:
        monkeypatch.setattr(mail, "parse", _boom)
        answer = _host_session("lost")
        assert no_smtp_server == []
        assert answer == {}
        assert h.emails()["total"] == 0


def test_a_trapped_session_never_reaches_a_transport_once_its_trap_is_gone(no_smtp_server: list[object]):
    # r2 fix review: a session opened under a trap has no server behind it, so its mail is never "sent"
    trap = install(FastAPI(), **{**OPTIONS, "email_dev_trap": True})
    smtp = smtplib.SMTP("smtp.example.test", 587, local_hostname="app.example.test")  # trapped: no socket
    trap.uninstall_capture()
    with harness() as h:  # the trap is off here
        answer = smtp.sendmail("app@example.test", ["b@example.test"], "Subject: orphan\r\n\r\nbody\r\n")
        smtp.quit()
        assert no_smtp_server == []
        assert answer == {}
        assert [m["sent"] for m in h.emails()["messages"]] == [False]


def _dropped_install(**options: Any) -> weakref.ref[Any]:
    """An app installed, never shut down nor uninstalled, then dropped: a weak reference to its recorder."""
    handle = install(FastAPI(), **{**OPTIONS, **options})
    return weakref.ref(handle.context.capture.mail)


def test_a_dropped_trap_app_no_longer_traps_or_records_another_apps_mail():
    # finding W7-E r2 #1: a never-shut-down app kept its recorder armed, and its trap, for the life of the process
    dead = _dropped_install(email_dev_trap=True)
    gc.collect()
    with harness() as h:
        h.send(subject="mine")
        assert len(h.sink.messages) == 1
        assert [m["sent"] for m in h.emails()["messages"]] == [True]
    assert dead() is None


def test_a_live_trap_app_never_traps_mail_sent_in_another_apps_request():
    # finding W7-E r2 #1: in a request only that app's recorder records, and only its trap decides
    other = install(FastAPI(), **{**OPTIONS, "email_dev_trap": True})  # alive, never shut down
    try:
        with harness() as h:
            h.app.add_api_route("/signup", lambda: h.send(subject="welcome"), methods=["POST"])
            assert h.client.post("/signup").status_code == 200
            assert len(h.sink.messages) == 1
            report = h.emails()
            assert report["total"] == 1
            assert report["messages"][0]["sent"] is True
        recorder = other.context.capture.mail
        assert recorder is not None
        assert recorder.entries() == []
    finally:
        other.uninstall_capture()


def _from_a_plain_thread(h: Harness) -> None:
    worker = threading.Thread(target=h.send, kwargs={"subject": "from a thread"})
    worker.start()
    worker.join()


def _from_a_websocket(h: Harness) -> None:
    @h.app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:  # the capture middleware sets no request for a websocket scope
        await socket.accept()
        h.send(subject="from a websocket")
        await socket.close()

    with h.client.websocket_connect("/ws"):
        pass


@pytest.mark.parametrize("outside", [_from_a_plain_thread, _from_a_websocket])
def test_outside_a_request_a_live_trap_app_never_traps_a_non_trap_apps_mail(outside: Callable[[Harness], None]):
    # finding W7-E r3 #1: outside a request the trap applies only when every live armed app has it on
    other = install(FastAPI(), **{**OPTIONS, "email_dev_trap": True})  # alive, never shut down
    try:
        with harness() as h:
            outside(h)
            assert len(h.sink.messages) == 1
            assert [m["sent"] for m in h.emails()["messages"]] == [True]
    finally:
        other.uninstall_capture()


def test_outside_a_request_the_trap_holds_when_every_live_app_has_it():
    with harness(email_dev_trap=True) as h:
        _from_a_plain_thread(h)
        assert h.sink.messages == []
        assert [m["sent"] for m in h.emails()["messages"]] == [False]


def test_the_trap_wraps_are_restored_once_no_live_app_has_the_trap_on():
    # finding W7-E r3 #2 (mutant M3): the connect, starttls wraps outlived the trap app while a non-trap app was alive
    originals = {name: smtplib.SMTP.__dict__[name] for name in ("connect", "starttls")}
    with harness() as h:
        trap = install(FastAPI(), **{**OPTIONS, "email_dev_trap": True})
        assert hasattr(smtplib.SMTP.__dict__["connect"], "__sharpit_original__")
        trap.uninstall_capture()
        assert smtplib.SMTP.__dict__["connect"] is originals["connect"]
        assert smtplib.SMTP.__dict__["starttls"] is originals["starttls"]
        h.send()
        assert len(h.sink.messages) == 1


def test_a_garbage_collector_callback_never_mutates_the_registry_while_it_is_being_updated():
    # finding W7-E r3 #3: _forget re-entered an RLock held by its own thread and rewrote _refs mid-update
    from sharpit.engine.capture import mail

    with harness() as h:
        recorder = h.handle.context.capture.mail
        assert recorder is not None
        before = mail._refs  # pyright: ignore[reportPrivateUsage]
        ref = next(r for r in before if r() is recorder)
        with mail._LOCK:  # pyright: ignore[reportPrivateUsage]
            mail._forget(ref)  # pyright: ignore[reportPrivateUsage]
            assert mail._refs is before  # pyright: ignore[reportPrivateUsage]


def test_a_failed_capture_outside_a_request_leaves_the_message_sent_and_recorded_as_sent(
    monkeypatch: pytest.MonkeyPatch,
):
    # finding W7-E r3 #5: another app recorded sent=False for a message the failed trap let through
    from sharpit.engine.capture import mail

    with smtp_sink() as sink:
        smtp = smtplib.SMTP("127.0.0.1", sink.port)  # connected before the traps armed: a real session
        failing = install(FastAPI(), **{**OPTIONS, "email_dev_trap": True})
        h = Harness(sink, email_dev_trap=True)
        try:
            recorder = failing.context.capture.mail
            assert recorder is not None
            real = mail.parse

            def parse(sender: str, recipients: object, raw: object, strict: Any, limit: int) -> Any:
                if strict is recorder._strict:  # pyright: ignore[reportPrivateUsage]
                    raise RuntimeError("capture failed")
                return real(sender, recipients, raw, strict, limit)  # type: ignore[arg-type]

            monkeypatch.setattr(mail, "parse", parse)
            worker = threading.Thread(
                target=smtp.sendmail, args=("app@example.test", ["b@example.test"], "Subject: kept\r\n\r\nbody\r\n")
            )
            worker.start()
            worker.join()
            smtp.quit()
            assert len(sink.messages) == 1
            assert [m["sent"] for m in h.emails()["messages"]] == [True]
        finally:
            h.handle.uninstall_capture()
            failing.uninstall_capture()


def test_mail_sent_in_a_request_carries_that_requests_id():
    # finding W7-E r2 #7: the journal event's requestId is the id of the request that sent the mail
    with harness() as h:
        h.app.add_api_route("/signup", lambda: h.send(subject="welcome"), methods=["POST"])
        assert h.client.post("/signup").status_code == 200
        journal = h.handle.context.capture.journal
        assert journal is not None
        http = journal.records("http")
        assert len(http) == 1
        request_id = http[0]["requestId"]
        assert isinstance(request_id, str)
        records = h.mail_records()
        assert len(records) == 1
        assert records[0]["requestId"] == request_id
        report = h.emails()
        assert report["total"] == 1
        assert report["messages"][0]["requestId"] == request_id


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
        records = h.mail_records()
        assert len(records) == 1  # finding W7-E r2 #5: the defect named before indexing
        record = records[0]
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
