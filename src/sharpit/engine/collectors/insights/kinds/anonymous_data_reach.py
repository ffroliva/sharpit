"""``anonymous-data-reach``: BootUI ``E/insights/AnonymousDataReach.java:26-43``."""

from sharpit.engine.collectors.insights.text import ANONYMOUS_ACCESS_NOT_APPLICABLE

KIND = "anonymous-data-reach"
TITLE = "Anonymous writes"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"http", "sql", "authorization"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = False

NOT_APPLICABLE_REASON = ANONYMOUS_ACCESS_NOT_APPLICABLE  # deviation: kind:anonymous-data-reach
