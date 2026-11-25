"""``anonymous-success-on-restricted-route``: BootUI ``E/insights/AnonymousSuccessOnRestrictedRoute.java:21-38``."""

KIND = "anonymous-success-on-restricted-route"
TITLE = "Anonymous success on a restricted route"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"http", "authorization"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = False

# BootUI decides from its authorization layer; FastAPI has none to observe (owner ruling, 0.10.0).
NOT_APPLICABLE_REASON = (
    "FastAPI makes no authorization decision that sharpit can observe, so anonymous access cannot be proven without "
    "running application code. The Security Advisor's SEC-AUTHZ-001 partly covers a route that forgot its security "
    "dependency, on state-changing routes only."
)
