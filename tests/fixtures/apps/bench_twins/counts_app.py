"""Twin of bench case D13 (GET /v0/counts/): a database error (no such table) swallowed into a zero count."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


def get_week_count(db: Session) -> int | None:
    try:
        return db.execute(text("SELECT count(*) FROM weeks")).scalar()
    except Exception:  # twin: week_count
        return 0
