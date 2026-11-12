"""Outgoing mail capture (BootUI ``EmailCaptureService`` and ``EmailStore``): the only module that touches ``smtplib``
and ``aiosmtplib``.

Wrap points are ``smtplib.SMTP.sendmail`` and ``aiosmtplib.SMTP.sendmail`` only (W0 spike c): ``send_message``, the SMTP
subclasses and fastapi-mail all end in ``sendmail``, so one message is captured once. ``aiosmtplib`` is never imported
here: it is wrapped when the host has already imported it (the attacher is retried at startup and on the first
request). The wrap is process-wide and shared by every armed recorder (one per ``install()``); the last one out
restores the originals.

Delivery is never affected: a capture that raises, a paused recorder and a disabled panel all leave the host's call
as it was. The one deliberate change is the dev trap (``email_dev_trap``), which answers the call itself, as BootUI's
``CapturingJavaMailSender`` skips the real send; it holds while paused, as BootUI's does.

Shortcut: only ``sendmail`` is wrapped, so a host that talks to a server through its own socket code is not seen;
``SMTP_SSL`` and ``LMTP`` inherit ``sendmail`` and are.
"""

from __future__ import annotations

import functools
import importlib.util
import smtplib
import sys
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from email import message_from_bytes, message_from_string, policy
from email.message import EmailMessage
from email.utils import formataddr, getaddresses
from typing import TYPE_CHECKING, Any, NamedTuple

from sharpit.engine import otel
from sharpit.engine.capture import wraps
from sharpit.engine.capture.correlation import REQUEST
from sharpit.engine.masking import Exposure, Masker

if TYPE_CHECKING:
    from sharpit.engine.capture import CaptureState

PANEL = "email"
SOURCE = "mail"
HOOK = "mail"
TAG = "mail"
TRUNCATED = "\n…[truncated, showing {limit} of {total} characters]"
_ORIGINAL = "__sharpit_original__"  # wraps.wrap's marker on a wrapper
_ASYNC_REFUSED = ({}, "OK")  # what aiosmtplib's sendmail answers when every recipient was accepted


class MailAttachment(NamedTuple):
    filename: str | None
    content_type: str | None
    size_bytes: int | None  # decoded size; None when the part has no decodable payload


class MailMessage(NamedTuple):
    sender: str | None
    to: tuple[str, ...]
    cc: tuple[str, ...]
    bcc: tuple[str, ...]
    subject: str | None
    text_body: str | None
    html_body: str | None
    attachments: tuple[MailAttachment, ...]


class MailEntry(NamedTuple):
    id: str
    timestamp_ms: int
    message: MailMessage
    sent: bool
    trace_id: str | None
    thread: str
    request_id: str | None


def _addresses(message: EmailMessage, name: str) -> tuple[str, ...]:
    values = [str(value) for value in message.get_all(name, [])]
    return tuple(formataddr(pair) for pair in getaddresses(values) if pair[1] or pair[0])


def _content(part: EmailMessage | None) -> str | None:
    if part is None:
        return None
    try:
        raw = str(part.get_content())
    except (LookupError, ValueError):  # an unknown charset or a broken encoding: the bytes, read leniently
        payload = part.get_payload(decode=True)
        raw = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else None
    return raw.replace("\r\n", "\n") if raw is not None else None


def _attachment(part: EmailMessage) -> MailAttachment:
    payload = part.get_payload(decode=True)
    return MailAttachment(
        part.get_filename(), part.get_content_type(), len(payload) if isinstance(payload, bytes) else None
    )


def _envelope_recipients(recipients: object) -> list[str]:
    if isinstance(recipients, str):
        return [recipients]
    return [str(r) for r in recipients] if isinstance(recipients, Sequence) else []  # pyright: ignore[reportUnknownVariableType]


def parse(sender: str, recipients: object, raw: str | bytes, strict: Masker, limit: int) -> MailMessage:
    """What ``sendmail`` was handed, as BootUI's ``MimeMessageInspector`` reads a message: bodies masked-then-cut at
    ``limit``, attachments as metadata only, bcc from the envelope (``send_message`` strips the header)."""
    parsed = (message_from_bytes if isinstance(raw, bytes) else message_from_string)(raw, policy=policy.default)  # type: ignore[arg-type]
    message = parsed if isinstance(parsed, EmailMessage) else EmailMessage()
    to, cc = _addresses(message, "To"), _addresses(message, "Cc")
    shown = {addr.lower() for _, addr in getaddresses([*to, *cc])}
    bcc = [*_addresses(message, "Bcc"), *(r for r in _envelope_recipients(recipients) if r.lower() not in shown)]
    header_from = _addresses(message, "From")
    subject = message.get("Subject")
    return MailMessage(
        header_from[0] if header_from else sender,
        to,
        cc,
        tuple(dict.fromkeys(bcc)),
        None if subject is None else str(subject),
        _bound(_content(message.get_body(preferencelist=("plain",))), limit, strict),  # type: ignore[arg-type]
        _bound(_content(message.get_body(preferencelist=("html",))), limit, strict),  # type: ignore[arg-type]
        tuple(_attachment(part) for part in message.iter_attachments()),  # type: ignore[arg-type]
    )


def _bound(body: str | None, limit: int, strict: Masker) -> str | None:
    """A body over ``limit`` is masked whole, strictly, before it is cut, so no secret is ever stored half."""
    if body is None or len(body) <= limit:
        return body
    return (strict.mask_text(body) or "")[:limit] + TRUNCATED.format(limit=limit, total=len(body))


class MailRecorder:
    """The bounded store, the capture policy and the registry entry (``name``) of one installed context."""

    name = HOOK

    def __init__(
        self,
        masker: Masker,
        capture: CaptureState,
        *,
        max_entries: int,
        max_body_length: int,
        dev_trap: bool,
        context_id: str | None = None,
        token: str | None = None,
    ) -> None:
        self.max_entries = max(1, max_entries)
        self.max_body_length = max(1, max_body_length)
        self.dev_trap = dev_trap
        self.paused = False
        self.teardown_registered = False
        self._strict = Masker(Exposure.MASKED, True, token, identity_key=masker.identity_key)
        self._capture = capture
        self._context_id = context_id
        self._entries: deque[MailEntry] = deque(maxlen=self.max_entries)
        self._sequence = 0
        self._lock = threading.Lock()

    # --- capture ------------------------------------------------------------------------------------------------------

    def record(self, sender: str, recipients: object, message: object) -> bool:
        """Store one outgoing message; answers whether the caller should still hand it to the real transport."""
        send = not self.dev_trap
        if self.paused or not isinstance(message, str | bytes):
            return send
        parsed = parse(sender, recipients, message, self._strict, self.max_body_length)
        info = REQUEST.get()
        with self._lock:
            self._sequence += 1
            entry = MailEntry(
                f"email-{self._sequence}",
                time.time_ns() // 1_000_000,
                parsed,
                send,
                otel.current_trace_id(),
                threading.current_thread().name,
                info.id if info is not None and info.context_id == self._context_id else None,
            )
            self._entries.appendleft(entry)
        self._publish(entry)
        return send

    def _publish(self, entry: MailEntry) -> None:
        journal = self._capture.journal
        if journal is None or (journal.sources is not None and SOURCE not in journal.sources):
            return
        try:  # built inside the guard: a failing event never loses the record it rides on
            message = entry.message
            journal.offer_flat(
                {
                    "source": SOURCE,
                    "recipients": len(message.to) + len(message.cc) + len(message.bcc),
                    "attachments": len(message.attachments),
                    "sent": entry.sent,
                    "failed": not entry.sent,
                    "traceId": entry.trace_id,
                    "requestId": entry.request_id,
                    "thread": entry.thread,
                    "durationNanos": -1,
                    "completedNanos": time.perf_counter_ns(),
                    "codePathStamp": 0,
                }
            )
        except Exception:  # noqa: BLE001 - publishing never disturbs the application's mail
            return

    # --- reads --------------------------------------------------------------------------------------------------------

    def entries(self) -> list[MailEntry]:
        with self._lock:
            return list(self._entries)

    def get(self, entry_id: str) -> MailEntry | None:
        with self._lock:
            return next((e for e in self._entries if e.id == entry_id), None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    # --- the capture-hook registry entry (low-footprint) ----------------------------------------------------------------

    def suspend(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def discard(self) -> None:
        self.clear()

    # --- arming -------------------------------------------------------------------------------------------------------

    def arm(self) -> bool:
        """Wrap what can be wrapped now; ``True`` when nothing more can come (``aiosmtplib`` absent or wrapped)."""
        with _LOCK:
            if self not in _ACTIVE:
                _ACTIVE.append(self)
            _wrap_senders()
            return "smtplib" in _WRAPPED and not _aiosmtplib_pending()

    def disarm(self) -> None:
        self.teardown_registered = False
        with _LOCK:
            if self in _ACTIVE:
                _ACTIVE.remove(self)
            if not _ACTIVE:
                _unwrap_senders()


# --- the process-wide wrap, shared by every armed recorder -------------------------------------------------------------

_LOCK = threading.RLock()
_ACTIVE: list[MailRecorder] = []
_WRAPPED: dict[str, Callable[[], bool]] = {}  # sender family -> its remover, in wrap order


def _dispatch(sender: str, recipients: object, message: object) -> bool:
    """Record on every armed recorder; ``True`` when the dev trap holds the real send back."""
    suppress = False
    for recorder in tuple(_ACTIVE):
        try:
            send = recorder.record(sender, recipients, message)
        except Exception:  # noqa: BLE001 - the host's mail is never lost to the capture
            send = not recorder.dev_trap
        suppress = suppress or not send
    return suppress


def _sync_sendmail(original: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(original)
    def sendmail(self: Any, from_addr: str, to_addrs: object, msg: object, *args: Any, **kwargs: Any) -> Any:
        if _ACTIVE and _dispatch(from_addr, to_addrs, msg):
            return {}
        return original(self, from_addr, to_addrs, msg, *args, **kwargs)

    return sendmail


def _async_sendmail(original: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(original)
    async def sendmail(self: Any, sender: str, recipients: object, message: object, *args: Any, **kwargs: Any) -> Any:
        if _ACTIVE and _dispatch(sender, recipients, message):
            return _ASYNC_REFUSED
        return await original(self, sender, recipients, message, *args, **kwargs)

    return sendmail


def _aiosmtplib_pending() -> bool:
    """The library is installed but the host has not imported it yet: the attacher is retried later."""
    if "aiosmtplib" in sys.modules:
        return False
    try:
        return importlib.util.find_spec("aiosmtplib") is not None
    except (ImportError, ValueError):
        return False


def _wrap_one(family: str, owner: type, make: Callable[[Callable[..., Any]], Callable[..., Any]]) -> None:
    if family in _WRAPPED:
        return
    remover = wraps.wrap(owner, "sendmail", make, tag=TAG)
    if remover is not None:
        _WRAPPED[family] = remover
    elif _ORIGINAL in getattr(owner.__dict__.get("sendmail"), "__dict__", {}):
        _WRAPPED[family] = lambda: False  # ours from an earlier arm whose remover could not run; still in place


def _wrap_senders() -> None:
    _wrap_one("smtplib", smtplib.SMTP, _sync_sendmail)
    module = sys.modules.get("aiosmtplib")
    owner = getattr(module, "SMTP", None)
    if isinstance(owner, type):
        _wrap_one("aiosmtplib", owner, _async_sendmail)


def _unwrap_senders() -> None:
    while _WRAPPED:
        _, remover = _WRAPPED.popitem()  # LIFO: the newest wrap first
        remover()


def attach(ctx: Any) -> Callable[[], None] | None:
    """A ``CaptureState.attachers`` entry: arm, and answer the remover once every sender that can be wrapped is."""
    recorder: MailRecorder | None = ctx.capture.mail
    if recorder is None:
        return None
    if recorder.arm():
        return recorder.disarm
    if not recorder.teardown_registered:  # aiosmtplib is installed but not imported: retried, undone at uninstall
        recorder.teardown_registered = True
        ctx.capture.teardowns.append(recorder.disarm)
    return None
