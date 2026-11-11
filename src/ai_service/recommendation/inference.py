"""Canonical request-scoped recommendation contract v1; no customer identity or storage."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Product(StrictModel):
    productId: UUID
    name: str = Field(min_length=1, max_length=512)
    category: str | None = Field(default=None, max_length=256)
    brand: str | None = Field(default=None, max_length=256)
    price: float | None = Field(default=None, ge=0)
    description: str = Field(default="", max_length=2000)
    popularity: float = Field(default=0, ge=0)


class Event(StrictModel):
    eventType: Literal["PRODUCT_VIEW", "PRODUCT_CLICK", "SEARCH", "WISHLIST_ADD", "WISHLIST_REMOVE"]
    productId: UUID | None = None
    query: str | None = Field(default=None, min_length=1, max_length=256)
    occurredAt: datetime

    @model_validator(mode="after")
    def valid_event(self):
        if self.occurredAt.tzinfo is None:
            raise ValueError("Timezone required")
        if self.eventType == "SEARCH":
            if self.productId is not None or self.query is None or not self.query.strip():
                raise ValueError("Invalid search event")
        elif self.productId is None or self.query is not None:
            raise ValueError("Invalid product event")
        return self


class InferenceRequest(StrictModel):
    candidates: list[Product] = Field(max_length=3000)
    recentEvents: list[Event] = Field(default_factory=list, max_length=500)
    wishlist: list[UUID] = Field(default_factory=list, max_length=3000)
    sourceProductId: UUID | None = None
    asOf: datetime
    limit: int = Field(default=10, ge=1, le=20, strict=True)

    @model_validator(mode="after")
    def valid_snapshot(self):
        if self.asOf.tzinfo is None:
            raise ValueError("Timezone required")
        ids = [p.productId for p in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate candidates")
        if not set(self.wishlist).issubset(ids):
            raise ValueError("Unknown wishlist product")
        return self


class RankedProduct(StrictModel):
    productId: UUID
    score: float = Field(ge=0)


class InferenceResponse(StrictModel):
    items: list[RankedProduct]
