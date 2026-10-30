"""Relaxed-binding-aware property-name matching (port of BootUI ``RelaxedNames``)."""

from __future__ import annotations


def canonicalize(value: str) -> str:
    """Lower-case, with ``_`` and ``-`` normalized to ``.``; length preserving."""
    return value.lower().replace("_", ".").replace("-", ".")


def contains(name: str | None, canonical_query: str | None) -> bool:
    """Whether ``name`` contains ``canonical_query`` once canonicalized. An empty query matches everything."""
    if not canonical_query:
        return True
    return name is not None and canonical_query in canonicalize(name)
