"""``after-commit-writes``: BootUI ``E/insights/AfterCommitWrites.java:29-46``."""

KIND = "after-commit-writes"
TITLE = "Writes after commit"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"app-event", "sql", "transaction"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = False
