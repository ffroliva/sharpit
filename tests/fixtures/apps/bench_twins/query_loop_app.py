"""Twin of bench task T3 (performances query loop): one session.get per id, no ORM relationship involved."""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class Performance(Base):
    __tablename__ = "performances"

    performance_id: Mapped[int] = mapped_column(primary_key=True)
    points: Mapped[float]


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(engine)
with Session(engine) as seed:
    seed.add_all(Performance(points=float(i)) for i in range(30))
    seed.commit()


def get_performances(db: Session, ids: list[int]) -> list[Performance | None]:
    return [db.get(Performance, performance_id) for performance_id in ids]


def get_points(db: Session, ids: list[int]) -> list[float | None]:
    statement = text("SELECT points FROM performances WHERE performance_id = :performance_id")
    return [db.execute(statement, {"performance_id": i}).scalar() for i in ids]
