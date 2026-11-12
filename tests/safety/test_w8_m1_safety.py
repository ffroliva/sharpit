"""Alembic migrate (W8 M1): the panel's GETs stay pure; the one action is refused by every gate."""

PANEL = "alembic"
GET_ROWS = ["/sharpit/api/alembic/migrations"]
WRITE_ROWS = [("POST", "/sharpit/api/alembic/migrate")]
TOOL_ARGS = {}
TOOL_SEEDS = {}
