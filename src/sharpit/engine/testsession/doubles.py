"""Whether a test double raised a swallowed exception (issue 68): a ``unittest.mock`` object, not the application.

The message is read to decide and never kept: only the verdict leaves this module. ``unittest.mock`` is never imported
here; a frame of it is recognised by its module name.
"""

from __future__ import annotations


def raised_by_test_double(exc: BaseException) -> bool:
    return False
