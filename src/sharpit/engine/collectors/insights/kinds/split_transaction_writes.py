"""``split-transaction-writes``: BootUI ``E/insights/SplitTransactionWrites.java:25-42``."""

KIND = "split-transaction-writes"
TITLE = "Writes split across transactions"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"sql", "transaction"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = False
