"""``lazy-sql-after-handler``: BootUI ``E/insights/LazySqlAfterHandler.java:45-72``."""

KIND = "lazy-sql-after-handler"
TITLE = "SQL after the handler returned"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"http", "sql"})
OPTIONAL_READS: frozenset[str] = frozenset({"transaction"})
IMPLEMENTED = False
