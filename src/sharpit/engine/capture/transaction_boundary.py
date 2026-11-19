"""Observed transaction boundaries, not the propagation declared on an application function."""

from __future__ import annotations

from enum import StrEnum


class TransactionBoundary(StrEnum):
    NEW = "NEW"
    REQUIRES_NEW = "REQUIRES_NEW"
    NESTED = "NESTED"
    UNKNOWN = "UNKNOWN"


def observed(known: bool, nested: bool, savepoint: bool) -> TransactionBoundary:
    return TransactionBoundary.NEW
