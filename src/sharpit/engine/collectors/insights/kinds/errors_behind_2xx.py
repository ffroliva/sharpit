"""``errors-behind-2xx``: BootUI ``E/insights/ErrorsBehind2xx.java:63-90``."""

KIND = "errors-behind-2xx"
TITLE = "Errors behind 2xx responses"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"http"})
OPTIONAL_READS: frozenset[str] = frozenset({"transaction", "exception", "log", "rest-client", "fault-tolerance"})
IMPLEMENTED = False
