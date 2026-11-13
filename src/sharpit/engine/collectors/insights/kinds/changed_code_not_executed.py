"""``changed-code-not-executed``: BootUI ``E/insights/ChangedCodeNotExecuted.java:52-69``."""

KIND = "changed-code-not-executed"
TITLE = "Changed code not executed"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset()
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = False
USES_REQUESTS = False  # BootUI unitKinds() is empty: no request is examined
