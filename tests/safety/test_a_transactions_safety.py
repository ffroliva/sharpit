"""Transactions panel routes included in the shared safety matrix."""

PANEL = "transactions"
GET_ROWS = ["/sharpit/api/transactions", "/sharpit/api/transactions/stream"]
WRITE_ROWS = [
    ("POST", "/sharpit/api/transactions/clear"),
    ("POST", "/sharpit/api/transactions/recording"),
]
