"""``transaction-across-remote-call``: BootUI ``E/insights/TransactionAcrossRemoteCall.java:36-58``."""

KIND = "transaction-across-remote-call"
TITLE = "Transactions open across remote calls"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"transaction"})
OPTIONAL_READS: frozenset[str] = frozenset({"connection", "rest-client", "ai"})
IMPLEMENTED = False
