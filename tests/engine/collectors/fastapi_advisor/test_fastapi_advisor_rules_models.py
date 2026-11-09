"""Model rules (WAVE-B §7: FAPI-PYD-001 Pydantic v1 API, dict responses without a response model)."""

from __future__ import annotations

from pathlib import Path

from .support import messages, run_rules

# ``pydantic`` is never imported: the rules read the source statically; stand-in bases keep the module executable
MODELS = """
class BaseModel:
    pass


def ConfigDict(**kwargs):
    return kwargs


class Legacy(BaseModel):
    name: str

    class Config:
        extra = "forbid"


class FromOrm(BaseModel):
    model_config = ConfigDict(orm_mode=True)


class Modern(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def as_dict():
    return {"ok": True}


def as_model():
    return Modern()
"""


def test_pydantic_v1_config_class_flagged(tmp_path: Path) -> None:
    found = messages(run_rules(tmp_path, MODELS, {}), "FASTAPI-PYD-001")
    assert len(found) == 1
    assert "class Config in Legacy" in found[0]


def test_orm_mode_flagged(tmp_path: Path) -> None:
    found = messages(run_rules(tmp_path, MODELS, {}), "FASTAPI-PYD-001")
    assert len(found) == 1
    assert "orm_mode" in found[0]
    assert "Modern" not in found[0]


def test_missing_response_model_on_dict_return(tmp_path: Path) -> None:
    routes = {"GET /dict": "as_dict", "GET /model": "as_model", "GET /declared": "as_dict"}
    evaluation = run_rules(tmp_path, MODELS, routes, response_models={"GET /declared": object})
    found = messages(evaluation, "FASTAPI-RESP-001")
    assert len(found) == 1
    assert "GET /dict" in found[0]
