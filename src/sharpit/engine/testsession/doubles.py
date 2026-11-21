"""Whether a test double raised a swallowed exception (issue 68): a ``unittest.mock`` object, not the application.

The message is read to decide and never kept: only the verdict leaves this module. ``unittest.mock`` is never imported
here; a frame of it is recognised by its module name.
"""

from __future__ import annotations

import re

_MODULE = "unittest.mock"
# the class names ``unittest.mock`` prints in its errors (``object MagicMock can't be used in 'await' expression``)
_NAMES = re.compile(r"\b(?:NonCallable)?(?:Magic|Async|Property)?Mock\b")
_READ = 1000  # characters of one argument that are read


def _in_mock_frame(exc: BaseException) -> bool:
    link = exc.__traceback__
    while link is not None:
        name = link.tb_frame.f_globals.get("__name__")
        if isinstance(name, str) and (name == _MODULE or name.startswith(f"{_MODULE}.")):
            return True
        link = link.tb_next
    return False


def _names_a_double(exc: BaseException) -> bool:
    """The text arguments only: ``str(exc)`` would run the exception's own code inside a monitoring callback."""
    return any(isinstance(arg, str) and _NAMES.search(arg[:_READ]) is not None for arg in exc.args)


def raised_by_test_double(exc: BaseException) -> bool:
    """True when a frame of ``unittest.mock`` is on the exception's traceback or its text names a mock class."""
    return _in_mock_frame(exc) or _names_a_double(exc)
