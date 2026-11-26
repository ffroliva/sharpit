"""BootUI wording for security-sinks rows."""

import re

SEEN_ONCE = " Seen in one request so far."
OTHER = (
    "Request input reached more sinks than this table keeps apart; their parameters and"
    " sinks are counted here. Restart the application to see them again."
)
_ARGUMENT = re.compile(r"^(.*), argument (\d+)$")


def _command(name: str) -> str:
    return "the executable" if name.startswith("(") else f"`{name}`"


def detail(kind: str, parameter: str | None, target: str | None, confirmed: bool) -> str:
    """Describe an observation without asserting that it is a vulnerability."""
    name = f"`{parameter if parameter is not None else 'a parameter'}`"
    if kind == "command":
        argument = _ARGUMENT.fullmatch(target) if target is not None else None
        if argument is not None:
            fact = (
                f"Request input reached this command unchanged: the value of {name} appeared in argument "
                f"{argument.group(2)} of {_command(argument.group(1))}. Check that it is validated."
            )
        else:
            fact = (
                f"Request input reached this command unchanged: the value of {name} appeared in it. "
                "Check that it is validated."
            )
    elif kind == "file path":
        fact = (
            f"Request input reached this file path unchanged: the value of {name} appeared in it. "
            "Check that it is validated and cannot leave its directory."
        )
    else:
        fact = (
            f"Request input reached this sink unchanged: the value of {name} appeared in it. "
            "Check that it is validated."
        )
    return fact if confirmed else fact + SEEN_ONCE
