"""``large-persistence-context``: BootUI ``E/insights/LargePersistenceContext.java:23-40``."""

KIND = "large-persistence-context"
TITLE = "Large persistence contexts"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"orm"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = False
