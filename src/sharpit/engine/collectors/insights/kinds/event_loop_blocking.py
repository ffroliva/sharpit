"""``event-loop-blocking``: BootUI ``E/insights/EventLoopBlocking.java:28-45``."""

KIND = "event-loop-blocking"
TITLE = "Blocking on event loops"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"sql"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = False
