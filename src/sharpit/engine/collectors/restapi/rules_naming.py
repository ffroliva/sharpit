"""REST API naming rule checks."""

from __future__ import annotations

from sharpit.engine.collectors.restapi.rules_common import (
    IRREGULAR_PLURALS,
    UNCOUNTABLE,
    VERB_STANDALONE,
    VERBS,
    VERSION,
    Check,
    each,
    shared_is_collection,
    shared_static,
    shared_words,
)
from sharpit.engine.spi import ApiRouteInfo


def _name001(route: ApiRouteInfo) -> str | None:
    for segment in shared_static(route.path):
        words = shared_words(segment)
        if segment.lower() in VERB_STANDALONE or (len(words) > 1 and words[0] in VERBS):
            return "verb in path"
    return None


def _name002(route: ApiRouteInfo) -> str | None:
    if "GET" not in route.methods or not shared_is_collection(route):
        return None
    static = [s for s in shared_static(route.path) if not VERSION.fullmatch(s)]
    if not static:
        return None
    words = shared_words(static[-1])
    noun = words[-1] if words else ""
    if not noun.isalpha() or noun.endswith("s") or noun in IRREGULAR_PLURALS or noun in UNCOUNTABLE:
        return None
    return f"singular collection name '{static[-1]}'"


def _name003(route: ApiRouteInfo) -> str | None:
    for segment in shared_static(route.path):
        if segment != segment.lower() or "_" in segment:
            return f"segment '{segment}' is not lowercase kebab-case"
    return None


CHECKS: dict[str, Check] = {
    "RAPI-NAME-001": each(_name001),
    "RAPI-NAME-002": each(_name002),
    "RAPI-NAME-003": each(_name003),
}
