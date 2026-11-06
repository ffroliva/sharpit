"""SQL text: dialect naming, lexing and rendering. Only this package imports its own internals."""

from __future__ import annotations

from sharpit.engine.sqltext.constants import MASK
from sharpit.engine.sqltext.dialect import Dialect, dialect_of_name
from sharpit.engine.sqltext.lexer import (
    SPACE_CHARS,
    Candidate,
    HandLexer,
    Kind,
    Range,
    Scan,
    SqlLexer,
    quoted_body,
)
from sharpit.engine.sqltext.render import collapse_placeholder_lists, secrets, shape, shown

LEXER: SqlLexer = HandLexer()
"""The one lexer. The facade reads it at each call, so the contract suite and a test can swap it."""

__all__ = [
    "LEXER",
    "MASK",
    "SPACE_CHARS",
    "Candidate",
    "Dialect",
    "HandLexer",
    "Kind",
    "Range",
    "Scan",
    "SqlLexer",
    "collapse_placeholder_lists",
    "dialect_of_name",
    "quoted_body",
    "secrets",
    "shape",
    "shown",
]
