"""Model rules over app source and route metadata: Pydantic v1 API, dict responses without a response model."""

from __future__ import annotations

from sharpit.engine.advisors.rules import RuleDefinition

PYDANTIC_V1 = RuleDefinition(
    "FASTAPI-PYD-001",
    "Pydantic v1 API in use",
    "Configuration",
    "MEDIUM",
    "Pydantic v1 idioms (an inner class Config, orm_mode, @validator, pydantic.v1 imports, BaseSettings from "
    "pydantic) are deprecated in Pydantic v2 and removed from FastAPI's supported path.",
    "Use model_config = ConfigDict(...), from_attributes=True, @field_validator and pydantic-settings.",
    "https://docs.pydantic.dev/latest/migration/",
)
DICT_RESPONSE = RuleDefinition(
    "FASTAPI-RESP-001",
    "Endpoint returns a dict without a response model",
    "Web and HTTP",
    "LOW",
    "An endpoint that returns a plain dict with no response model is neither validated nor filtered on the way "
    "out, and its OpenAPI schema says nothing about the body.",
    "Declare a Pydantic response model (response_model= or a return annotation).",
    "https://fastapi.tiangolo.com/tutorial/response-model/",
)
RULES = (PYDANTIC_V1, DICT_RESPONSE)
