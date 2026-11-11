"""``heap-growth-after-gc``: BootUI ``E/insights/HeapGrowthAfterGc.java:39-56``."""

KIND = "heap-growth-after-gc"
TITLE = "Heap growth after GC"
MINIMUM_TIER = "REQUEST_ID"
READS: frozenset[str] = frozenset({"gc"})
OPTIONAL_READS: frozenset[str] = frozenset()
IMPLEMENTED = False
