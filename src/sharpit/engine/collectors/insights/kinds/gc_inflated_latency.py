"""``gc-inflated-latency``: BootUI ``E/insights/GcInflatedLatency.java:42-59``."""

KIND = "gc-inflated-latency"
TITLE = "Pauses during slow requests"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"http", "gc", "resources"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = False
