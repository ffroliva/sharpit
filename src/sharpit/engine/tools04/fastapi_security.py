from __future__ import annotations

from sharpit.engine.collectors.appsecurity import model_of, security_report
from sharpit.engine.tools import _NONE, Tool  # pyright: ignore[reportPrivateUsage]

TOOLS = (
    Tool(
        "get_fastapi_security",
        "Return the current FastAPI security filter-chain and authentication configuration report. This passive read "
        "does not authenticate, authorize, or send a request through a chain.",
        _NONE,
        "fastapi-security",
        False,
        lambda c, _a: security_report(model_of(c.ctx)),
    ),
)
COMMANDS = {"get_fastapi_security": "fastapi-security"}
