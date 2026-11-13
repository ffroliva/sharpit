"""Outgoing mail capture (BootUI ``EmailCaptureService`` and ``EmailStore``): the only module that touches ``smtplib``
and ``aiosmtplib``.

The capture point is ``smtplib.SMTP.sendmail`` and ``aiosmtplib.SMTP.sendmail`` only (W0 spike c): ``send_message``,
the SMTP subclasses and fastapi-mail all end in ``sendmail``, so one message is captured once. ``aiosmtplib`` is never
imported here: it is wrapped when the host has already imported it, or the moment the host imports it later (a
``sys.meta_path`` finder scoped to that one name, left in place and inert without a recorder). The wrap is
process-wide and holds every armed recorder (one per ``install()``) by a weak reference, so an app dropped without
shutting down stops capturing once it is garbage-collected; the last one out restores the originals.
In a request, only that app's recorder records the message and only its trap decides; outside a request (a worker
thread, a websocket handler, startup, a script) the message is no app's, so every live recorder records it and the trap
holds it only when every live armed app has the trap on (a non-trap app's real mail is never swallowed).

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
``SMTP_SSL`` and ``LMTP`` inherit ``sendmail`` and are (an ``LMTP`` unix socket is not trapped, nor is a subclass whose
own ``connect`` opens its own socket).
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import importlib.abc
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
    return tuple(_address(pair) for pair in getaddresses(values) if pair[1] or pair[0])


def _address(pair: tuple[str, str]) -> str:
    try:
        return formataddr(pair)
    except UnicodeEncodeError:  # SMTPUTF8: formataddr only encodes ASCII; keep the text as written
        name, address = pair
        quoted = '"' + name.replace(chr(92), chr(92) * 2).replace('"', chr(92) + '"') + '"'
        return f"{quoted} <{address}>" if name and address else address or name


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

    def capture(self, sender: str, recipients: object, message: object) -> MailMessage | None:
        """The message as stored, or ``None`` when this recorder keeps nothing (paused, or not a string)."""
        if self.paused or not isinstance(message, str | bytes):
            return None
        return parse(sender, recipients, message, self._strict, self.max_body_length)

    def store(self, parsed: MailMessage, sent: bool) -> None:
        """Keep one captured message as ``sent`` (whether it reached the transport)."""
        info = REQUEST.get()
        with self._lock:
            self._sequence += 1
            entry = MailEntry(
                f"email-{self._sequence}",
                time.time_ns() // 1_000_000,
                parsed,
                sent,
                otel.current_trace_id(),
                threading.current_thread().name,
                info.id if info is not None and info.context_id == self.context_id else None,
            )
            self._entries.appendleft(entry)
        self._publish(entry)

    def record(self, sender: str, recipients: object, message: object, sent: bool | None = None) -> None:
        """Capture and store one message as ``sent`` (this recorder's own trap decides when not given)."""
        parsed = self.capture(sender, recipients, message)
        if parsed is not None:
            self.store(parsed, not self.dev_trap if sent is None else sent)

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
        """Wrap what can be wrapped now and watch for a later ``aiosmtplib``; ``True`` once ``smtplib`` and
        ``aiosmtplib`` are both wrapped (``False`` without it: retried by the attacher, torn down at uninstall)."""
        # _refs is swapped whole under the lock and read lock-free by the wrappers
        global _refs  # noqa: PLW0603
        with _LOCK:
            _prune()  # also drops what a skipped ``_forget`` left
            me = cast("MailRecorder", self)
            if not any(r is me for r in _live()):
                _refs = (*_refs, weakref.ref(me, _forget))
            _watch_import()  # first: an import after this line meets the hook, one before it is in sys.modules below
            _wrap_senders(sys.modules.get("aiosmtplib"), trap=_trap_on())
            return "smtplib" in _WRAPPED and "aiosmtplib" in _WRAPPED

    def disarm(self) -> None:
        self.teardown_registered = False
        with _LOCK:
            _prune(drop=self)


# --- the process-wide wrap, shared by every armed recorder -----------------------------------------------------

# A plain lock, not an RLock: a GC callback that fires on the thread inside ``arm`` or ``disarm`` must not re-enter and
# rewrite ``_refs`` mid-update, and ``_forget`` only ever tries it without blocking.
_LOCK = threading.Lock()
_refs: tuple[weakref.ref[MailRecorder], ...] = ()  # every armed recorder, held weakly
_WRAPPED: dict[str, Callable[[], bool]] = {}  # wrapped method -> its remover, in wrap order
_AIOSMTPLIB_CONNECT = "aiosmtplib.connect"
_TRAP_WRAPS = ("smtplib.connect", "smtplib.starttls", _AIOSMTPLIB_CONNECT)  # in place only while a trap is on


def _live() -> list[MailRecorder]:
    return [r for ref in _refs if (r := ref()) is not None]


def _unwrap(families: Sequence[str]) -> None:
    for family in families:
        if remover := _WRAPPED.pop(family, None):
            remover()


def _prune(*, dead: weakref.ref[MailRecorder] | None = None, drop: MailRecorder | None = None) -> None:
    """Under ``_LOCK``: forget the collected, ``dead`` and ``drop``; restore every wrap once no recorder is left, and
    the trap's once none has the trap on."""
    global _refs  # noqa: PLW0603
    _refs = tuple(ref for ref in _refs if ref is not dead and (r := ref()) is not None and r is not drop)
    live = _live()
    if not live:
        _unwrap(list(reversed(_WRAPPED)))  # the newest wrap first
    elif not _trap_on(live):
        _unwrap(_TRAP_WRAPS)


def _forget(dead: weakref.ref[MailRecorder]) -> None:
    """A recorder's app was garbage-collected without shutting down. Never blocks and never touches the registry while
    this thread (or another) is updating it: the dead reference is then pruned by the next ``arm`` or ``disarm``, and
    the wrappers already skip it."""
    if not _LOCK.acquire(blocking=False):
        return
    try:
        _prune(dead=dead)
    finally:
        _LOCK.release()


def _targets() -> list[MailRecorder]:
    """In a request, its own app's recorder only; outside one, every live recorder (the message is no app's)."""
    live = _live()
    info = REQUEST.get()
    return live if info is None else [r for r in live if r.context_id == info.context_id]


def _traps(targets: list[MailRecorder]) -> bool:
    """Whether the dev trap holds for these recorders: all of them have it on. In a request that is its own app's
    trap; outside one it is every live armed app's (BootUI's trap belongs to one app's sender, a mail no app owns is
    never swallowed on one app's say-so)."""
    return bool(targets) and all(r.dev_trap for r in targets)


def _trapping() -> bool:
    """Whether a session opened now is trapped."""
    try:
        return _traps(_targets())
    except Exception:  # noqa: BLE001 - never an error into the host's connect
        return False


def _dispatch(sender: str, recipients: object, message: object, trapped: bool) -> bool:
    """Capture on every targeted recorder; ``True`` when the real send is held back. A trap whose capture failed lets
    the message through, as BootUI's ``captureMime`` answers ``true`` when it cannot capture; a ``trapped`` session
    (opened under a trap) has no server behind it, so it is always held, even once its trap is gone. ``sent`` is worked
    out here, once, before anything is stored."""
    try:
        targets = _targets()
        want = _traps(targets)
    except Exception:  # noqa: BLE001 - the host's mail is never lost to the capture
        return trapped
    captured: list[tuple[MailRecorder, MailMessage]] = []
    complete = True
    for recorder in targets:
        try:
            parsed = recorder.capture(sender, recipients, message)
        except Exception:  # noqa: BLE001 - the host's mail is never lost to the capture
            complete = False
            continue
        if parsed is not None:
            captured.append((recorder, parsed))
    held = trapped or (want and complete)
    for recorder, parsed in captured:
        try:
            recorder.store(parsed, not held)
        except Exception:  # noqa: BLE001, S112 - storing never disturbs the application's mail
            continue
    return held


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
        await asyncio.sleep(0)  # aiosmtplib awaits these; the trapped session has nothing to wait for
        return self._answer(_replies(args[0] if args else b""))

    async def execute_data_command(self, *_args: object, **_options: object) -> Any:
        await asyncio.sleep(0)
        return self._answer(_ACCEPTED)

    async def start_tls(self, *_args: object, **_options: object) -> Any:
        await asyncio.sleep(0)
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


class _LateImport(importlib.abc.MetaPathFinder):
    """Scoped to ``aiosmtplib`` alone: when the host imports it after ``install()`` (inside a handler, a background
    task) the module is wrapped the moment it finishes loading, before the host can use it. BootUI's post-processor
    wraps every ``JavaMailSender`` bean as it is created, so a late one is never missed either. It answers from the
    finders behind it, so another import hook still sees the import, and it is inert without an armed recorder.

    Fails closed while a dev trap is on (a sharpit-only choice: BootUI fails open, returning a bean it could not wrap):
    a module that cannot be wrapped is not imported, ``ImportError`` naming the trap, because loaded unwrapped it would
    send real mail. With no trap on, the module loads unwrapped, as it always did."""

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> Any:
        if fullname != "aiosmtplib" or not _refs:
            return None
        try:
            behind = sys.meta_path[sys.meta_path.index(self) + 1 :]
            spec = next(
                (
                    s
                    for f in behind
                    if hasattr(f, "find_spec") and (s := f.find_spec(fullname, path, target)) is not None
                ),
                None,
            )
            if spec is None:  # not installed: nothing loads, so nothing can send
                return None
            exec_module = spec.loader.exec_module  # type: ignore[union-attr]
            if not getattr(exec_module, _PATCHED, False):  # a shared loader is probed again and again: patch it once

                @functools.wraps(exec_module)
                def wrapped(module: Any) -> None:
                    exec_module(module)
                    if module.__name__ == "aiosmtplib":  # a shared loader (zipimport) loads other modules too
                        _wrap_loaded_or_refuse(module)

                setattr(wrapped, _PATCHED, True)
                spec.loader.exec_module = wrapped  # type: ignore[union-attr]
        except ImportError:  # a finder's own failure: nothing loads, so the host sees that error, not ours
            raise
        except Exception as exc:  # noqa: BLE001 - never a bare error into the host's import
            return _refuse_or_pass(exc)
        return spec


_FINDER = _LateImport()
_PATCHED = "__sharpit_late_import__"
_seen: weakref.ref[type] | None = None  # the aiosmtplib.SMTP class the senders were last wrapped on
_REFUSED = "sharpit's dev trap could not wrap aiosmtplib, so it is not imported: unwrapped it would send real mail"


def _trap_on(live: list[MailRecorder] | None = None) -> bool:
    return any(r.dev_trap for r in (_live() if live is None else live))


def _refuse_or_pass(cause: Exception) -> None:
    """With a trap on, refuse the import; otherwise ``None`` (load as it is)."""
    if _trap_on():
        raise ImportError(_REFUSED, name="aiosmtplib") from cause


def _wrap_loaded_or_refuse(module: Any, *, blocking: bool = True) -> None:
    try:
        _wrap_loaded(module, blocking=blocking)
    except Exception as exc:  # noqa: BLE001 - the capture never fails a host's import, unless a trap must hold
        if _trap_on():  # none of the package may stay loaded: ``from aiosmtplib.smtp import ...`` would skip the hook
            for name in [n for n in sys.modules if n == "aiosmtplib" or n.startswith("aiosmtplib.")]:
                sys.modules.pop(name, None)
        _refuse_or_pass(exc)


def _wrap_loaded(module: Any, *, blocking: bool = True) -> None:
    """``aiosmtplib`` has just loaded: wrap ``module`` (again, for a re-import) for every armed recorder, or raise. With
    a trap on, both the capture and the transport wrap must hold, or the module is refused. ``blocking=False`` (a
    request's event-loop thread) skips the wrap when the registry is busy: the next request start covers it."""
    # a finalizer on the thread inside arm() must not hang the import
    if not _LOCK.acquire(timeout=5 if blocking else 0):
        if blocking:
            raise TimeoutError("the mail registry stayed locked")
        return
    try:
        live = _live()
        if live:
            _unwrap((_AIOSMTPLIB_CONNECT, "aiosmtplib"))  # a stale record of an earlier module object
            _wrap_senders(module, trap=_trap_on(live))
            if _trap_on(live) and not {"aiosmtplib", _AIOSMTPLIB_CONNECT} <= _WRAPPED.keys():
                raise RuntimeError("aiosmtplib.SMTP could not be wrapped")
    finally:
        _LOCK.release()


def ensure_wrapped() -> None:
    """The second layer behind ``_LateImport``: an ``aiosmtplib`` that loaded past the hook (another library's finder
    answered first), or whose ``SMTP`` class a reload replaced, is wrapped, or refused as the hook refuses, at the next
    request start. Never blocks the event loop (a busy registry skips this request), never from a read (a GET patches
    nothing); with nothing changed it costs one ``sys.modules`` lookup and an identity check."""
    module = sys.modules.get("aiosmtplib")
    if module is None or not _refs or (_seen is not None and _seen() is getattr(module, "SMTP", None)):
        return
    if getattr(getattr(module, "__spec__", None), "_initializing", False):  # another thread is importing it now
        return
    with contextlib.suppress(Exception):  # a refusal has already dropped the package; the request goes on
        _wrap_loaded_or_refuse(module, blocking=False)


def _watch_import() -> None:
    """Until ``aiosmtplib`` is imported, watch for it. The hook stays on ``sys.meta_path`` (inert with no recorder
    armed): removing it could shift a list the import system is iterating."""
    if "aiosmtplib" not in sys.modules and _FINDER not in sys.meta_path:
        sys.meta_path.insert(0, _FINDER)


def _wrap_one(family: str, owner: type, name: str, make: Callable[[Callable[..., Any]], Callable[..., Any]]) -> None:
    if family in _WRAPPED:
        return
    remover = wraps.wrap(owner, name, make, tag=TAG)
    if remover is not None:
        _WRAPPED[family] = remover
    elif _ORIGINAL in getattr(owner.__dict__.get(name), "__dict__", {}):
        _WRAPPED[family] = lambda: False  # ours from an earlier arm whose remover could not run; still in place


def _wrap_senders(module: Any, *, trap: bool) -> None:
    """The capture wraps; the trap's transport wraps only once a recorder with the trap on is armed, so a host without
    the trap keeps its own connect."""
    _wrap_one("smtplib", smtplib.SMTP, "sendmail", _sync_sendmail)
    if trap:
        _wrap_one("smtplib.connect", smtplib.SMTP, "connect", _sync_connect)
        _wrap_one("smtplib.starttls", smtplib.SMTP, "starttls", _sync_starttls)
    owner = getattr(module, "SMTP", None)
    if not isinstance(owner, type):
        return
    _wrap_one("aiosmtplib", owner, "sendmail", _async_sendmail)
    global _seen  # noqa: PLW0603
    _seen = weakref.ref(owner)
    response = getattr(module, "SMTPResponse", None)
    if trap and callable(response):  # without it the trap stays sendmail-only for this aiosmtplib
        _wrap_one(_AIOSMTPLIB_CONNECT, owner, "_create_connection", _async_create_connection(response))


def attach(ctx: Any) -> Callable[[], None] | None:
    """A ``CaptureState.attachers`` entry: arm, and answer the remover once every sender is wrapped. Until then it is
    retried (startup, first request) and undone at uninstall; an ``aiosmtplib`` imported later is wrapped by
    ``_LateImport`` as it loads."""
    recorder: MailRecorder | None = ctx.capture.mail
    if recorder is None:
        return None
    if recorder.arm():
        return recorder.disarm
    if not recorder.teardown_registered:
        recorder.teardown_registered = True
        ctx.capture.teardowns.append(recorder.disarm)
    return None
