"""Outgoing mail capture (BootUI ``EmailCaptureService`` and ``EmailStore``): the only module that touches ``smtplib``
and ``aiosmtplib``."""

from __future__ import annotations

PANEL = "email"
SOURCE = "mail"
HOOK = "mail"


class MailRecorder:
    """Stub: records nothing until the feature lands."""

    def record(self, sender: str, recipients: object, message: object) -> bool:
        return True
