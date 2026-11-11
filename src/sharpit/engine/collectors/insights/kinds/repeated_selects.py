"""``repeated-selects``: BootUI ``E/insights/RepeatedSelects.java:101-123``."""

KIND = "repeated-selects"
TITLE = "Repeated SELECTs"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"sql"})
OPTIONAL_READS: frozenset[str] = frozenset({"transaction"})
IMPLEMENTED = False
