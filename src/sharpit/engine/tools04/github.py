"""The read-only GitHub dashboard tool."""

from pathlib import Path

from sharpit.engine.collectors.github.dashboard import GitHubDashboard
from sharpit.engine.context import SharpitContext
from sharpit.engine.tools import Tool


def github_dashboard(ctx: SharpitContext) -> GitHubDashboard:
    return ctx.lazy("github-dashboard", lambda: GitHubDashboard(Path.cwd, ctx.settings))


TOOLS = (
    Tool(
        "get_github_dashboard",
        "Return local repository identity plus the last cached GitHub dashboard report. This passive read never calls "
        "GitHub; only the panel's explicit refresh action can use the network.",
        {"type": "object", "properties": {}, "additionalProperties": False},
        "github",
        False,
        lambda call, _args: github_dashboard(call.ctx).dashboard(),
    ),
)
COMMANDS = {"get_github_dashboard": "github"}
