from __future__ import annotations

from sharpit.engine.collectors.config.profiles import profiles_report
from sharpit.engine.tools import _NONE, Tool  # pyright: ignore[reportPrivateUsage]

TOOLS = (
    Tool(
        "get_profile_diff",
        "Return the current active-profile configuration comparison using masked local configuration data. Use it to "
        "identify profile-specific differences without changing profiles.",
        _NONE,
        "profile-diff",
        False,
        lambda c, _a: profiles_report(c.ctx),
    ),
)
COMMANDS = {"get_profile_diff": "profile diff"}
