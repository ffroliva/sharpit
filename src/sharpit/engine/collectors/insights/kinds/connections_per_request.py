"""``connections-per-request``: BootUI ``E/insights/ConnectionsPerRequest.java:24-41``."""

KIND = "connections-per-request"
TITLE = "Connections held together"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"connection"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = False
