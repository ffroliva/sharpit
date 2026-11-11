"""``proxy-bypass``: BootUI ``E/insights/ProxyBypass.java:36-58``."""

KIND = "proxy-bypass"
TITLE = "Proxy bypass"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"sql"})
OPTIONAL_READS: frozenset[str] = frozenset({"transaction", "cache"})
IMPLEMENTED = False
