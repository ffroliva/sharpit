"""``route-time-breakdown``: BootUI ``E/insights/RouteTimeBreakdown.java:137-164``."""

KIND = "route-time-breakdown"
TITLE = "Route time breakdown"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"http"})
OPTIONAL_READS: frozenset[str] = frozenset(
    {"sql", "connection", "rest-client", "authorization", "ai", "orm", "messaging"}
)
IMPLEMENTED = False
