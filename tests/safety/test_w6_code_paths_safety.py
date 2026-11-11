"""Code Paths reads have no side effects, and the panel gates its reads and its probe actions."""

PANEL = "code-paths"
GET_ROWS = [
    "/sharpit/api/code-paths",
    "/sharpit/api/code-paths/route",
    "/sharpit/api/code-paths/beans",
    "/sharpit/api/code-paths/requests/{id}",
    "/sharpit/api/code-paths/probes",
]
WRITE_ROWS = [
    ("POST", "/sharpit/api/code-paths/probes"),
    ("POST", "/sharpit/api/code-paths/probes/{id}/stop"),
    ("DELETE", "/sharpit/api/code-paths/probes/{id}"),
]
