"""The Email panel's read side (BootUI ``EmailCaptureService.list/get``, ``EmailsReport``, ``EmailEmlRenderer``).

Masking happens here, at read time with the live policy, as BootUI's does: ``mask-content`` (off by default) masks every
field unless the exposure is FULL; below FULL, sharpit's own secret scrub runs on top (deviation D-E1, owner
ruling OQ1):
BootUI shows a captured password-reset link as it is, sharpit masks the secret in it. The ``.eml`` is rendered from the
masked message, never from the stored one.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from email.utils import format_datetime
from typing import TYPE_CHECKING, Any, cast

from sharpit.engine.capture.mail import MailAttachment, MailEntry, MailRecorder
from sharpit.engine.masking import MASK, Exposure

if TYPE_CHECKING:
    from sharpit.engine.context import SharpitContext

NOT_INSTALLED = "Email capture is not installed"


def unavailable_report(reason: str, max_entries: int) -> dict[str, Any]:
    """``EmailsReport.unavailable``."""
    return {
        "available": False,
        "unavailableReason": reason,
        "devTrapEnabled": False,
        "maxEntries": max_entries,
        "total": 0,
        "messages": [],
    }


def _scrubber(ctx: SharpitContext) -> Callable[[str | None], str | None]:
    token = ctx.token

    def scrub(text: str | None) -> str | None:
        if text is None:
            return None
        if token and token in text:
            text = text.replace(token, MASK)  # a generated console token is not in the masker's list
        shown = ctx.masker.mask_text(text)
        return MASK if shown is None else shown  # METADATA_ONLY withholds the text: a fixed marker, never the text

    return scrub


def _attachment(attachment: MailAttachment, scrub: Callable[[str | None], str | None]) -> dict[str, Any]:
    return {
        "filename": scrub(attachment.filename),
        "contentType": attachment.content_type,
        "sizeBytes": attachment.size_bytes,
    }


def _message(ctx: SharpitContext, entry: MailEntry) -> dict[str, Any]:
    message = entry.message
    scrub = _scrubber(ctx)
    hidden = ctx.settings.email_mask_content and ctx.settings.expose_values is not Exposure.FULL

    def field(text: str | None) -> str | None:
        return (MASK if text is not None else None) if hidden else scrub(text)

    def each(values: tuple[str, ...]) -> list[str]:
        return [MASK if hidden else (scrub(value) or MASK) for value in values]

    return {
        "id": entry.id,
        "timestamp": entry.timestamp_ms,
        "from": MASK if hidden and message.sender is not None else scrub(message.sender),
        "to": each(message.to),
        "cc": each(message.cc),
        "bcc": each(message.bcc),
        "subject": MASK if hidden else field(message.subject),
        "textBody": field(message.text_body),
        "htmlBody": field(message.html_body),
        "attachments": [_attachment(a, scrub) for a in message.attachments],
        "sent": entry.sent,
        "traceId": entry.trace_id,
        "thread": entry.thread,
        "requestId": entry.request_id,
    }


def _recorder(ctx: SharpitContext) -> MailRecorder | None:
    recorder = ctx.capture.mail
    return recorder if isinstance(recorder, MailRecorder) else None


def email_report(ctx: SharpitContext) -> dict[str, Any]:
    recorder = _recorder(ctx)
    if recorder is None:
        return unavailable_report(NOT_INSTALLED, ctx.settings.email_max_entries)
    entries = recorder.entries()
    return {
        "available": True,
        "unavailableReason": None,
        "devTrapEnabled": recorder.dev_trap,
        "maxEntries": recorder.max_entries,
        "total": len(entries),
        "messages": [_message(ctx, e) for e in entries],
    }


def email_message(ctx: SharpitContext, email_id: str) -> dict[str, Any] | None:
    recorder = _recorder(ctx)
    entry = recorder.get(email_id) if recorder is not None else None
    return None if entry is None else _message(ctx, entry)


def clear_emails(ctx: SharpitContext) -> None:
    recorder = _recorder(ctx)
    if recorder is not None:
        recorder.clear()


def _address_header(name: str, addresses: object) -> str:
    if not isinstance(addresses, list) or not addresses:
        return ""
    return f"{name}: {', '.join(str(a) for a in cast('list[object]', addresses))}\r\n"


def render_eml(message: Mapping[str, Any]) -> str:
    """``EmailEmlRenderer.render`` over the masked message: ``message/rfc822``, CRLF line ends."""
    when = format_datetime(datetime.fromtimestamp(message["timestamp"] / 1000, UTC), usegmt=True)
    html = message["htmlBody"]
    out = [
        f"From: {message['from'] or ''}\r\n",
        _address_header("To", message["to"]),
        _address_header("Cc", message["cc"]),
        _address_header("Bcc", message["bcc"]),
        f"Subject: {message['subject'] or ''}\r\n",
        f"Date: {when}\r\n",
        f"Content-Type: {'text/html' if html is not None else 'text/plain'}; charset=UTF-8\r\n\r\n",
        html if html is not None else message["textBody"] or "",
    ]
    if message["attachments"]:
        out.append("\r\n\r\n--- Attachments (metadata only, content not captured) ---\r\n")
        out.extend(f"{a['filename']} ({a['contentType']}, {a['sizeBytes']} bytes)\r\n" for a in message["attachments"])
    return "".join(out)
