"""``readonly-candidate-transaction``: BootUI ``E/insights/ReadOnlyCandidateTransaction.java:63-80``."""

KIND = "readonly-candidate-transaction"
TITLE = "Read-write transactions that only read"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"orm", "transaction", "sql"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = False
