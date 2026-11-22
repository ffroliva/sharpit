"""Helpers for recording the FastAPI console response corpus."""

from tests.console_corpus.harness import build_app, get_routes, record
from tests.console_corpus.normalise import NORMALISERS, normalise

__all__ = ["NORMALISERS", "build_app", "get_routes", "normalise", "record"]
