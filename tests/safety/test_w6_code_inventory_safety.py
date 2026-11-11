"""Code Inventory reads have no side effects, and the panel gates every route."""

PANEL = "code-inventory"
GET_ROWS = [
    "/sharpit/api/code-inventory",
    "/sharpit/api/code-inventory/changes",
    "/sharpit/api/code-inventory/methods",
    "/sharpit/api/code-inventory/dependencies",
]
WRITE_ROWS: list[tuple[str, str]] = []
