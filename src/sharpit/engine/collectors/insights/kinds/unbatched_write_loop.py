"""``unbatched-write-loop``: BootUI ``E/insights/UnbatchedWriteLoop.java:33-55``."""

KIND = "unbatched-write-loop"
TITLE = "Unbatched write loops"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"sql"})
OPTIONAL_READS: frozenset[str] = frozenset({"transaction"})
IMPLEMENTED = False
