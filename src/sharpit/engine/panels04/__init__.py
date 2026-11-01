from __future__ import annotations

from . import architecture, data, database_advisor, fastapi, fastapi_security, mysql, postgresql, security, security_logs
from . import sqlalchemy_statistics, traces, transactions

IMPLEMENTED = {
    "data": data.IMPLEMENTED,
    "transactions": transactions.IMPLEMENTED,
    "postgresql": postgresql.IMPLEMENTED,
    "mysql": mysql.IMPLEMENTED,
    "traces": traces.IMPLEMENTED,
    "security": security.IMPLEMENTED,
    "security-logs": security_logs.IMPLEMENTED,
    "database-advisor": database_advisor.IMPLEMENTED,
    "architecture": architecture.IMPLEMENTED,
    "sqlalchemy-statistics": sqlalchemy_statistics.IMPLEMENTED,
    "fastapi-security": fastapi_security.IMPLEMENTED,
    "fastapi": fastapi.IMPLEMENTED,
}
