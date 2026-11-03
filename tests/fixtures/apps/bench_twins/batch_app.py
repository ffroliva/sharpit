"""Twin of bench clean cases C02/C06 for U8: batched loads that a per-row counter would mistake for N+1.

2,500 teams make ``selectinload`` issue five identical ``IN`` batches (its chunk is 500); ``players_of`` is one explicit
``WHERE team_id IN (...)`` over every id.
"""

from sqlalchemy import ForeignKey, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, selectinload
from sqlalchemy.pool import StaticPool

TEAMS = 2500


class Base(DeclarativeBase):
    pass


class Team(Base):
    __tablename__ = "team"

    team_id: Mapped[int] = mapped_column(primary_key=True)
    players: Mapped[list["Player"]] = relationship()


class Player(Base):
    __tablename__ = "player"

    player_id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("team.team_id"))


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(engine)
with Session(engine) as seed:
    seed.add_all(Team(players=[Player()]) for _ in range(TEAMS))
    seed.commit()


def teams_with_players(db: Session) -> list[Team]:
    return list(db.scalars(select(Team).options(selectinload(Team.players))))


def players_of(db: Session, team_ids: list[int]) -> list[Player]:
    return list(db.scalars(select(Player).where(Player.team_id.in_(team_ids))))
