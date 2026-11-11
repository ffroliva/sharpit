"""``work-after-response``: BootUI ``E/insights/WorkAfterResponse.java:39-66``."""

KIND = "work-after-response"
TITLE = "Work after the response"
MINIMUM_TIER = "PROPAGATED"
READS: frozenset[str] = frozenset({"http", "agent.executors"})
OPTIONAL_READS: frozenset[str] = frozenset({"sql", "rest-client", "messaging"})
IMPLEMENTED = False
