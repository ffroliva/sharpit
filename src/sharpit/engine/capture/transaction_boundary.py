"""Observed transaction boundaries, not the propagation declared on an application function."""

from __future__ import annotations

from enum import StrEnum


class TransactionBoundary(StrEnum):
    NEW = "NEW"
    REQUIRES_NEW = "REQUIRES_NEW"
    NESTED = "NESTED"
    UNKNOWN = "UNKNOWN"


def observed(known: bool, nested: bool, savepoint: bool) -> TransactionBoundary:
    if not known:
        return TransactionBoundary.UNKNOWN
    if savepoint:
        return TransactionBoundary.NESTED
    return TransactionBoundary.REQUIRES_NEW if nested else TransactionBoundary.NEW
