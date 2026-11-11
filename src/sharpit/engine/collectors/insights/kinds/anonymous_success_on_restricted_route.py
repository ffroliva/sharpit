"""``anonymous-success-on-restricted-route``: BootUI ``E/insights/AnonymousSuccessOnRestrictedRoute.java:21-38``."""

KIND = "anonymous-success-on-restricted-route"
TITLE = "Anonymous success on a restricted route"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"http", "authorization"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = False
