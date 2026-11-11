"""``safe-method-dml``: BootUI ``E/insights/SafeMethodDml.java:26-43``."""

KIND = "safe-method-dml"
TITLE = "Writes in GET requests"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"http", "sql"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = False
