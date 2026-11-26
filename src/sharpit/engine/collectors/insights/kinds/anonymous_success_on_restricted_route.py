"""``anonymous-success-on-restricted-route``: BootUI ``E/insights/AnonymousSuccessOnRestrictedRoute.java:21-38``."""

from sharpit.engine.collectors.insights.text import ANONYMOUS_ACCESS_NOT_APPLICABLE

KIND = "anonymous-success-on-restricted-route"
TITLE = "Anonymous success on a restricted route"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"http", "authorization"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = False

NOT_APPLICABLE_REASON = ANONYMOUS_ACCESS_NOT_APPLICABLE  # deviation: kind:anonymous-success-on-restricted-route
