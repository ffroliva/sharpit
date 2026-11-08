"""Twin of the bench clean base data layer (odsc-west-2024-1 api/ with base.patch): sync SQLAlchemy, eager loads."""

from sqlalchemy import ForeignKey, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, selectinload
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"

    player_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    performances: Mapped[list["Performance"]] = relationship(back_populates="player")


class Performance(Base):
    __tablename__ = "performances"

    performance_id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.player_id"))
    points: Mapped[float]
    player: Mapped[Player] = relationship(back_populates="performances")


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(engine)
with Session(engine) as seed:
    seed.add_all(Player(name=f"p{i}", performances=[Performance(points=float(i))]) for i in range(30))
    seed.commit()


def get_players(db: Session, skip: int = 0, limit: int = 100) -> list[Player]:
    query = select(Player).options(selectinload(Player.performances)).offset(skip).limit(limit)
    return list(db.scalars(query))


def get_performances(db: Session, skip: int = 0, limit: int = 100) -> list[Performance]:
    return list(db.scalars(select(Performance).offset(skip).limit(limit)))
