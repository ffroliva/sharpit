"""Twin of the bench clean base main.py: the FastAPI app, which test_crud.py never imports."""

from clean_app import engine, get_players
from sqlalchemy.orm import Session

from fastapi import FastAPI

app = FastAPI()


@app.get("/v0/players/")
def read_players(skip: int = 0, limit: int = 100) -> list[str]:
    with Session(engine) as db:
        return [player.name for player in get_players(db, skip, limit)]
