"""Spike F1 T4: a missing attribute swallowed by a broad handler becomes a wrong count served with HTTP 200."""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI()


class Week:
    def __init__(self, number: int) -> None:
        self.number = number  # the planted defect: no ``week_id``


WEEKS = [Week(1), Week(2)]


def get_week_count() -> int:
    try:
        return len({week.week_id for week in WEEKS})  # type: ignore[attr-defined]
    except Exception:
        return 0


@app.get("/weeks")
def weeks() -> list[int]:
    return [week.number for week in WEEKS]


@app.get("/weeks/count")
def week_count() -> dict[str, int]:
    return {"week_count": get_week_count()}
