"""``anonymous-data-reach``: BootUI ``E/insights/AnonymousDataReach.java:26-43``."""

KIND = "anonymous-data-reach"
TITLE = "Anonymous writes"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"http", "sql", "authorization"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = False
