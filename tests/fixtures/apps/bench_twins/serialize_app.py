"""Twin of bench cases D01/D02/D04-D06: the response model reads a lazy collection while FastAPI serializes it.

The lazy loads run inside pydantic's serializer on TestClient's worker thread, so no application frame is on the stack.
"""

from collections.abc import Iterator
from typing import Annotated

from pydantic import BaseModel, ConfigDict
from sqlalchemy import ForeignKey, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship
from sqlalchemy.pool import StaticPool

from fastapi import Depends, FastAPI


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "player"

    player_id: Mapped[int] = mapped_column(primary_key=True)
    performances: Mapped[list["Performance"]] = relationship(back_populates="player")  # twin: declared


class Performance(Base):
    __tablename__ = "performance"

    performance_id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("player.player_id"))
    player: Mapped[Player] = relationship(back_populates="performances")


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(engine)
with Session(engine) as seed:
    seed.add_all(Player(performances=[Performance()]) for _ in range(10))
    seed.commit()


class PerformanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    performance_id: int


class PlayerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    player_id: int
    performances: list[PerformanceOut] = []


def get_db() -> Iterator[Session]:
    with Session(engine) as db:
        yield db


def get_players(db: Session) -> list[Player]:
    return list(db.query(Player).all())  # the D01 regression: selectinload(Player.performances) removed


app = FastAPI()


@app.get("/v0/players/", response_model=list[PlayerOut])
def read_players(db: Annotated[Session, Depends(get_db)]) -> list[Player]:
    return get_players(db)
