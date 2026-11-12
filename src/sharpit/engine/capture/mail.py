"""Outgoing mail capture (BootUI ``EmailCaptureService`` and ``EmailStore``): the only module that touches ``smtplib``
and ``aiosmtplib``.

The capture point is ``smtplib.SMTP.sendmail`` and ``aiosmtplib.SMTP.sendmail`` only (W0 spike c): ``send_message``,
the SMTP subclasses and fastapi-mail all end in ``sendmail``, so one message is captured once. ``aiosmtplib`` is never
imported here: it is wrapped when the host has already imported it (the attacher is retried at startup and on the first
request). The wrap is process-wide and holds every armed recorder (one per ``install()``) by a weak reference, so an app
dropped without shutting down stops capturing once it is garbage-collected; the last one out restores the originals.
In a request, only that app's recorder records the message and only its trap decides; outside a request (a worker
thread, startup, a script) the message is no app's, so every live recorder records it and any trap among them holds it.

Delivery is never affected: a capture that raises, a paused recorder and a disabled panel all leave the host's call
as it was. The one deliberate change is the dev trap (``email_dev_trap``), which, like BootUI's
``CapturingJavaMailSender``, never reaches the transport. ``sendmail`` alone cannot skip it: ``smtplib.SMTP()`` and
``aiosmtplib``'s ``connect`` open the socket, EHLO, STARTTLS and log in before ``sendmail`` runs. So once a trap is
armed, ``smtplib.SMTP.connect`` and ``starttls`` and ``aiosmtplib.SMTP._create_connection`` are wrapped too: a session
opened under the trap talks to an in-memory server that accepts every command, and no socket is opened. A trap holds
while paused, as BootUI's does. A capture that fails under the trap lets the message through, as BootUI's
``captureMime`` answers ``true``; a trapped session has no transport to send it on, so there it is neither sent nor
stored (proposed deviation D-E2).

Shortcut: only ``sendmail`` is captured, so a host that talks to a server through its own socket code is not seen;
``SMTP_SSL`` and ``LMTP`` inherit ``sendmail`` and are (an ``LMTP`` unix socket is not trapped).
"""

from __future__ import annotations

import functools
import importlib.metadata
import smtplib
import sys
import threading
import time
import weakref
from collections import deque
from collections.abc import Callable, Sequence
from email import message_from_bytes, message_from_string, policy
from email.message import EmailMessage
from email.utils import formataddr, getaddresses
from typing import TYPE_CHECKING, Any, NamedTuple, cast

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
# what aiosmtplib's sendmail answers when every recipient was accepted
_ASYNC_REFUSED: tuple[dict[str, Any], str] = ({}, "OK")
# the trap's in-memory server: its reply per command verb (the first four letters); anything else is accepted
_REPLIES: dict[str, tuple[bytes, ...]] = {
    "EHLO": (
        b"250-sharpit dev trap\r\n",
        b"250-8BITMIME\r\n",
        b"250-SMTPUTF8\r\n",
        b"250-STARTTLS\r\n",
        b"250 AUTH PLAIN LOGIN\r\n",
    ),
    "AUTH": (b"235 accepted, never checked\r\n",),
    "DATA": (b"354 go on\r\n",),
    "QUIT": (b"221 bye\r\n",),
}
_ACCEPTED = (b"250 ok\r\n",)
_NO_TLS = "sharpit dev trap: no TLS, nothing left the process"


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
    return [str(r) for r in cast("Sequence[object]", recipients)] if isinstance(recipients, Sequence) else []


def parse(sender: str, recipients: object, raw: str | bytes, strict: Masker, limit: int) -> MailMessage:
    """What ``sendmail`` was handed, as BootUI's ``MimeMessageInspector`` reads a message: bodies masked-then-cut at
    ``limit``, attachments as metadata only, bcc from the envelope (``send_message`` strips the header)."""
    message = (
        message_from_bytes(raw, policy=policy.default)
        if isinstance(raw, bytes)
        else message_from_string(raw, policy=policy.default)
    )
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
        self.context_id = context_id
        self._entries: deque[MailEntry] = deque(maxlen=self.max_entries)
        self._sequence = 0
        self._lock = threading.Lock()

    # --- capture ------------------------------------------------------------------------------------------------------

    def record(self, sender: str, recipients: object, message: object, sent: bool | None = None) -> None:
        """Store one outgoing message as ``sent`` (whether it reaches the transport; this recorder's own trap decides
        when not given)."""
        if self.paused or not isinstance(message, str | bytes):
            return
        send = not self.dev_trap if sent is None else sent
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
                info.id if info is not None and info.context_id == self.context_id else None,
            )
            self._entries.appendleft(entry)
        self._publish(entry)

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

    # --- the capture-hook registry entry (low-footprint) ----------------------------------------------------------

    def suspend(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def discard(self) -> None:
        self.clear()

    # --- arming -------------------------------------------------------------------------------------------------------

    def arm(self) -> bool:
        """Wrap what can be wrapped now; ``True`` when nothing more can come (``aiosmtplib`` absent or wrapped)."""
        global _refs  # noqa: PLW0603 - swapped whole under the lock, read lock-free by the wrappers
        with _LOCK:
            live = [ref for ref in _refs if ref() is not None]  # also prunes what a skipped ``_forget`` left
            me = cast("MailRecorder", self)
            mine = [] if any(ref() is me for ref in live) else [weakref.ref(me, _forget)]
            _refs = (*live, *mine)
            _wrap_senders(trap=any(r.dev_trap for r in _live()))
            return "smtplib" in _WRAPPED and not _aiosmtplib_pending()

    def disarm(self) -> None:
        global _refs  # noqa: PLW0603
        self.teardown_registered = False
        with _LOCK:
            _refs = tuple(ref for ref in _refs if ref() not in (None, self))
            if not _refs:
                _unwrap_senders()


# --- the process-wide wrap, shared by every armed recorder -----------------------------------------------------

_LOCK = threading.RLock()
_refs: tuple[weakref.ref[MailRecorder], ...] = ()  # every armed recorder, held weakly
_WRAPPED: dict[str, Callable[[], bool]] = {}  # wrapped method -> its remover, in wrap order


def _live() -> list[MailRecorder]:
    return [r for ref in _refs if (r := ref()) is not None]


def _forget(dead: weakref.ref[MailRecorder]) -> None:
    """A recorder's app was garbage-collected without shutting down: drop it, and unwrap when it was the last."""
    global _refs  # noqa: PLW0603
    if not _LOCK.acquire(blocking=False):  # collected inside another thread's locked section: the next arm prunes it
        return
    try:
        _refs = tuple(ref for ref in _refs if ref is not dead and ref() is not None)
        if not _refs:
            _unwrap_senders()
    finally:
        _LOCK.release()


def _targets() -> list[MailRecorder]:
    """In a request, its own app's recorder only; outside one, every live recorder (the message is no app's)."""
    live = _live()
    info = REQUEST.get()
    return live if info is None else [r for r in live if r.context_id == info.context_id]


def _trapping() -> bool:
    """Whether a session opened now is trapped: a targeted recorder has the dev trap on."""
    try:
        return any(r.dev_trap for r in _targets())
    except Exception:  # noqa: BLE001 - never an error into the host's connect
        return False


def _dispatch(sender: str, recipients: object, message: object, trapped: bool) -> bool:
    """Record on every targeted recorder; ``True`` when a trap holds the real send back. A trap whose capture failed
    lets the message through, as BootUI's ``captureMime`` answers ``true`` when it cannot capture. A ``trapped``
    session (opened under a trap) has no server behind it, so it is always held, even once its trap is gone."""
    try:
        targets = _targets()
    except Exception:  # noqa: BLE001 - the host's mail is never lost to the capture
        return trapped
    sent = not (trapped or any(r.dev_trap for r in targets))
    held = [_held(recorder, sender, recipients, message, sent) for recorder in targets]  # every one records
    return trapped or any(held)


def _held(recorder: MailRecorder, sender: str, recipients: object, message: object, sent: bool) -> bool:
    """Whether this recorder's trap holds the message back: only when its capture succeeded."""
    try:
        recorder.record(sender, recipients, message, sent)
    except Exception:  # noqa: BLE001 - the host's mail is never lost to the capture
        return False
    return recorder.dev_trap


def _sync_sendmail(original: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(original)
    def sendmail(self: Any, from_addr: str, to_addrs: object, msg: object, *args: Any, **kwargs: Any) -> Any:
        if _refs and _dispatch(from_addr, to_addrs, msg, isinstance(getattr(self, "sock", None), _TrapPeer)):
            return {}
        return original(self, from_addr, to_addrs, msg, *args, **kwargs)

    return sendmail


def _async_sendmail(original: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(original)
    async def sendmail(self: Any, sender: str, recipients: object, message: object, *args: Any, **kwargs: Any) -> Any:
        trapped = isinstance(getattr(self, "protocol", None), _TrapProtocol)
        if _refs and _dispatch(sender, recipients, message, trapped):
            return _ASYNC_REFUSED
        return await original(self, sender, recipients, message, *args, **kwargs)

    return sendmail


# --- the dev trap's transport: a session opened under the trap never opens a socket ------------------------------


def _replies(command: bytes) -> tuple[bytes, ...]:
    return _REPLIES.get(command[:4].upper().decode("ascii", "replace"), _ACCEPTED)


class _TrapPeer:
    """``smtplib``'s socket for a trapped session: an in-memory server that accepts every command."""

    def __init__(self) -> None:
        self._lines: deque[bytes] = deque([b"220 sharpit dev trap\r\n"])
        self._data = False

    def sendall(self, data: bytes) -> None:
        if self._data:  # the message itself, up to its "." line
            self._data = not data.endswith(b"\r\n.\r\n")
            self._lines.extend(() if self._data else _ACCEPTED)
            return
        self._data = data[:4].upper() == b"DATA"
        self._lines.extend(_replies(data))

    def makefile(self, *_args: object) -> _TrapPeer:
        return self

    def readline(self, *_args: object) -> bytes:
        return self._lines.popleft() if self._lines else b""

    def close(self) -> None:
        self._lines.clear()


def _sync_connect(original: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(original)
    def connect(self: Any, *args: Any, **kwargs: Any) -> Any:
        if not (_refs and _trapping()):
            return original(self, *args, **kwargs)
        self.sock, self.file = _TrapPeer(), None
        return self.getreply()

    return connect


def _sync_starttls(original: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(original)
    def starttls(self: Any, *args: Any, **kwargs: Any) -> Any:
        if not isinstance(getattr(self, "sock", None), _TrapPeer):
            return original(self, *args, **kwargs)
        self.ehlo_or_helo_if_needed()
        self.helo_resp = self.ehlo_resp = None  # what the real one forgets after the handshake (RFC 3207)
        self.esmtp_features, self.does_esmtp = {}, False
        return (220, _NO_TLS.encode())

    return starttls


class _TrapTransport:
    def get_extra_info(self, _key: str, default: object = None) -> object:
        return default

    def is_closing(self) -> bool:
        return False

    def close(self) -> None:
        return None


class _TrapProtocol:
    """``aiosmtplib``'s ``SMTPProtocol`` for a trapped session: the same answers as ``_TrapPeer``."""

    is_connected = True

    def __init__(self, response: Callable[[int, str], Any]) -> None:
        self.transport = _TrapTransport()
        self._response = response

    def _answer(self, lines: tuple[bytes, ...]) -> Any:
        text = "\n".join(line[4:].decode("ascii").strip() for line in lines)
        return self._response(int(lines[0][:3]), text)

    async def execute_command(self, *args: bytes, **_options: object) -> Any:
        return self._answer(_replies(args[0] if args else b""))

    async def execute_data_command(self, *_args: object, **_options: object) -> Any:
        return self._answer(_ACCEPTED)

    async def start_tls(self, *_args: object, **_options: object) -> Any:
        return self._response(220, _NO_TLS)


def _async_create_connection(response: Callable[[int, str], Any]) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def make(original: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(original)
        async def _create_connection(self: Any, *args: Any, **kwargs: Any) -> Any:
            if not (_refs and _trapping()):
                return await original(self, *args, **kwargs)
            self.protocol = _TrapProtocol(response)
            self.transport = self.protocol.transport
            return response(220, "sharpit dev trap")

        return _create_connection

    return make


def _aiosmtplib_pending() -> bool:
    """The library is installed but the host has not imported it yet: the attacher is retried later."""
    if "aiosmtplib" in sys.modules:
        return False
    try:  # the distribution's metadata: nothing is imported (find_spec belongs to appsource alone)
        importlib.metadata.distribution("aiosmtplib")
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


def _wrap_one(family: str, owner: type, name: str, make: Callable[[Callable[..., Any]], Callable[..., Any]]) -> None:
    if family in _WRAPPED:
        return
    remover = wraps.wrap(owner, name, make, tag=TAG)
    if remover is not None:
        _WRAPPED[family] = remover
    elif _ORIGINAL in getattr(owner.__dict__.get(name), "__dict__", {}):
        _WRAPPED[family] = lambda: False  # ours from an earlier arm whose remover could not run; still in place


def _wrap_senders(*, trap: bool) -> None:
    """The capture wraps; the trap's transport wraps only once a recorder with the trap on is armed, so a host without
    the trap keeps its own connect."""
    _wrap_one("smtplib", smtplib.SMTP, "sendmail", _sync_sendmail)
    if trap:
        _wrap_one("smtplib.connect", smtplib.SMTP, "connect", _sync_connect)
        _wrap_one("smtplib.starttls", smtplib.SMTP, "starttls", _sync_starttls)
    module = sys.modules.get("aiosmtplib")
    owner = getattr(module, "SMTP", None)
    if not isinstance(owner, type):
        return
    _wrap_one("aiosmtplib", owner, "sendmail", _async_sendmail)
    response = getattr(module, "SMTPResponse", None)
    if trap and callable(response):  # without it the trap stays sendmail-only for this aiosmtplib
        _wrap_one("aiosmtplib.connect", owner, "_create_connection", _async_create_connection(response))


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
