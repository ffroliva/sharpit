"""A throwaway SMTP sink bound to 127.0.0.1 port 0, for the mail capture tests: it records what it was handed."""

from __future__ import annotations

import smtplib
import socketserver
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from email.message import EmailMessage
from typing import Any

from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        sink: SmtpSink = self.server.sink  # type: ignore[attr-defined]
        self._say("220 sink ready")
        sender, recipients = "", []
        while line := self.rfile.readline():
            command = line.decode("latin-1").strip()
            verb = command.split(" ", 1)[0].upper()
            if verb == "MAIL":
                sender, recipients = command.split(":", 1)[1].strip().strip("<>").split(">")[0], []
                self._say("250 ok")
            elif verb == "RCPT":
                recipients.append(command.split(":", 1)[1].strip().strip("<>").split(">")[0])
                self._say("250 ok")
            elif verb == "DATA":
                self._say("354 go")
                data = b""
                while (chunk := self.rfile.readline()) not in (b".\r\n", b""):
                    data += chunk
                sink.messages.append((sender, tuple(recipients), data))
                self._say("250 queued")
            elif verb == "QUIT":
                self._say("221 bye")
                return
            else:
                self._say("250 ok")

    def _say(self, text: str) -> None:
        self.wfile.write(f"{text}\r\n".encode("latin-1"))
        self.wfile.flush()


class SmtpSink:
    def __init__(self) -> None:
        self.messages: list[tuple[str, tuple[str, ...], bytes]] = []
        self._server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Handler)
        self._server.daemon_threads = True
        self._server.sink = self  # type: ignore[attr-defined]
        self.port: int = self._server.server_address[1]

    def start(self) -> None:
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@contextmanager
def smtp_sink() -> Iterator[SmtpSink]:
    sink = SmtpSink()
    sink.start()
    try:
        yield sink
    finally:
        sink.stop()


API = "/sharpit/api"
LOCAL = ("127.0.0.1", 50000)
OPTIONS: dict[str, Any] = {
    "enabled": "ON",
    "show_banner": False,
    "config_scan": False,
    "authentication_token": "console-token-secret-123",
}


class Harness:
    """One installed app, one sink and a client: ``send`` hands mail to the sink through the real ``smtplib``."""

    def __init__(self, sink: SmtpSink, **options: Any) -> None:
        self.sink = sink
        self.app = FastAPI()
        self.handle = install(self.app, **{**OPTIONS, **options})
        self.client = TestClient(self.app, base_url="http://localhost", client=LOCAL)

    def send(
        self,
        subject: str = "hello",
        body: str = "plain body",
        *,
        sender: str = "app@example.test",
        to: tuple[str, ...] = ("alice@example.test",),
        cc: tuple[str, ...] = (),
        bcc: tuple[str, ...] = (),
        html: str | None = None,
        attachment: bytes | None = None,
    ) -> None:
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = sender, ", ".join(to), subject
        if cc:
            message["Cc"] = ", ".join(cc)
        message.set_content(body)
        if html is not None:
            message.add_alternative(html, subtype="html")
        if attachment is not None:
            message.add_attachment(attachment, maintype="application", subtype="pdf", filename="invoice.pdf")
        with smtplib.SMTP("127.0.0.1", self.sink.port) as smtp:
            smtp.send_message(message, to_addrs=[*to, *cc, *bcc])

    def sendmail(
        self, raw: str, *, sender: str = "app@example.test", to: tuple[str, ...] = ("a@example.test",)
    ) -> None:
        with smtplib.SMTP("127.0.0.1", self.sink.port) as smtp:
            smtp.sendmail(sender, list(to), raw)

    def emails(self) -> dict[str, Any]:
        response = self.client.get(f"{API}/email")
        assert response.status_code == 200
        return response.json()

    def mail_records(self) -> tuple[dict[str, object], ...]:
        journal = self.handle.context.capture.journal
        assert journal is not None
        return journal.records("mail")

    def hook(self, name: str) -> Any:
        return next((h for h in self.handle.context.capture.hooks.hooks() if h.name == name), None)


@contextmanager
def harness(**options: Any) -> Iterator[Harness]:
    with smtp_sink() as sink:
        h = Harness(sink, **options)
        try:
            yield h
        finally:
            h.handle.uninstall_capture()
