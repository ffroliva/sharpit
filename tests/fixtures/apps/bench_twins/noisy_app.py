"""Twin of the bench app's rest-api surface: trailing-slash routes and loose DTOs give notes, no gate failure."""

from fastapi import FastAPI

app = FastAPI()


@app.get("/v0/players/")
def players() -> list[str]:
    return []


@app.get("/v0/performances/")
def performances() -> list[str]:
    return []


@app.get("/v0/leagues/")
def leagues() -> list[str]:
    return []


@app.get("/v0/teams/")
def teams() -> list[str]:
    return []


@app.get("/v0/counts/")
def counts() -> dict[str, int]:
    return {}


@app.post("/getUsers")
def get_users() -> list[str]:
    return []
