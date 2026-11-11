"""``connection-reacquisition``: BootUI ``E/insights/ConnectionReacquisition.java:32-54``."""

KIND = "connection-reacquisition"
TITLE = "Connections re-acquired in a session"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"orm"})
OPTIONAL_READS: frozenset[str] = frozenset({"sql", "transaction"})
IMPLEMENTED = False
