"""SQL text: dialect naming, lexing and rendering. Only this package imports its own internals."""

from __future__ import annotations

from sharpit.engine.sqltext.constants import MASK
from sharpit.engine.sqltext.dialect import Dialect
from sharpit.engine.sqltext.lexer import (
    SPACE_CHARS,
    Candidate,
    HandLexer,
    Kind,
    Range,
    Scan,
    SqlLexer,
    block_closer,
    quoted_body,
    reads_two_ways,
)
from sharpit.engine.sqltext.render import collapse_placeholder_lists, shape, shown

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
    "block_closer",
    "collapse_placeholder_lists",
    "quoted_body",
    "reads_two_ways",
    "shape",
    "shown",
]
