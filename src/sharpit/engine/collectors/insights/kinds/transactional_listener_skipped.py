"""``transactional-listener-skipped``: BootUI ``E/insights/TransactionalListenerSkipped.java:24-41``."""

KIND = "transactional-listener-skipped"
TITLE = "Transactional listeners skipped"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"app-event"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = False
