"""Email reads have no side effects, and DELETE /email is an action the read-only gates refuse."""

PANEL = "email"
GET_ROWS = [
    "/sharpit/api/email",
    "/sharpit/api/email/{id}",
    "/sharpit/api/email/{id}/eml",
]
WRITE_ROWS = [("DELETE", "/sharpit/api/email")]
PATH_PARAMS = {"id": "email-1"}
TOOL_ARGS = {}
TOOL_SEEDS = {}
