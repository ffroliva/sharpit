from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]


app = FastAPI()
engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(engine)
with Session(engine) as session:
    session.add_all(Team(name=f"team-{i}") for i in range(52))
    session.commit()


@app.get("/teams")
def teams(skip: int = 0, limit: int = 5) -> list[str]:
    with Session(engine) as session:
        rows = session.query(Team).all()
    return [team.name for team in rows[skip : skip + limit]]
