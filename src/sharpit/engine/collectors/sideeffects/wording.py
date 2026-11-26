"""BootUI wording for security-sinks rows."""

SEEN_ONCE = " Seen in one request so far."
OTHER = (
    "Request input reached more sinks than this table keeps apart; their parameters and"
    " sinks are counted here. Clear the recording to see them again."
)


def detail(kind: str, parameter: str | None, target: str | None, confirmed: bool) -> str:
    """Describe an observation without asserting that it is a vulnerability."""
    return ""
