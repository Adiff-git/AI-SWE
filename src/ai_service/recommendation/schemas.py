"""Proposed recommendation contracts, pending Backend Team agreement."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
    limit: int = Field(default=10, ge=1, le=100, strict=True)


class RecommendationResponse(BaseModel):
    product_ids: list[str] = Field(default_factory=list)
    status: Literal["not_implemented"] = "not_implemented"
