from sharpit.engine.capture.securitylogs import context_report
from sharpit.engine.tools import _LIMIT_ONLY, Tool  # pyright: ignore[reportPrivateUsage]

TOOLS = (
    Tool(
        "get_security_logs",
        "Return a bounded, newest-first snapshot of authentication and authorization audit events. Correlate "
        "timestamps and principals with live activity.",
        _LIMIT_ONLY,
        "security-logs",
        False,
        lambda c, a: context_report(c.ctx, limit=a["limit"]),
    ),
)
COMMANDS = {"get_security_logs": "security-logs"}
