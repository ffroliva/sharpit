from __future__ import annotations

from sharpit.engine.capture.mailview import email_report
from sharpit.engine.tools import _NONE, Tool  # pyright: ignore[reportPrivateUsage]

TOOLS = (
    Tool(
        "get_emails",
        "Return the bounded local email-capture inventory with content governed by sharpit exposure policy and "
        "secret-shaped text always masked. This does not send, download, or delete any message.",
        _NONE,
        "email",
        False,
        lambda c, _a: email_report(c.ctx),
    ),
)
COMMANDS = {"get_emails": "mail"}
