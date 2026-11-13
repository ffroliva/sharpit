"""``slow-flush``: BootUI ``E/insights/SlowFlush.java:32-49``."""

KIND = "slow-flush"
TITLE = "Slow Hibernate flushes"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"orm"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = False
