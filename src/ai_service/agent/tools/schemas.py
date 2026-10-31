"""Internal read-only DTOs, not an agreed Backend API contract."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

type Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=128, pattern=r"^[^\x00-\x1f\x7f]+$"
    ),
]
type ShortText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=200, pattern=r"^[^\x00-\x1f\x7f]+$"
    ),
]
type Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
type ToolSource = Literal["fake", "unavailable"]


class SearchProductsArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    query: ShortText
    category: Identifier | None = None
    min_price: float | None = Field(default=None, ge=0, le=1e15, allow_inf_nan=False)
    max_price: float | None = Field(default=None, ge=0, le=1e15, allow_inf_nan=False)
    currency: Currency | None = None

    @model_validator(mode="after")
    def validate_prices(self) -> SearchProductsArgs:
        if (self.min_price is not None or self.max_price is not None) and self.currency is None:
            raise ValueError("Price constraints require an explicit currency")
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError("Minimum price exceeds maximum price")
        return self


class ProductDetailsArgs(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    product_id: Identifier


class Price(BaseModel):
    """Read-only currency units, not a payment/monetary-arithmetic contract."""

    model_config = ConfigDict(strict=True, extra="ignore", frozen=True)

    amount: float = Field(ge=0, le=1e15, allow_inf_nan=False)
    currency: Currency


class Product(BaseModel):
    """Only these bounded fields can be exposed to the model."""

    model_config = ConfigDict(strict=True, extra="ignore", frozen=True)

    product_id: Identifier
    name: ShortText
    category: Identifier | None = None
    price: Price | None = None
    specifications: dict[Identifier, ShortText] = Field(default_factory=dict, max_length=10)


class ProductSearchData(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    products: list[Product] = Field(max_length=5)
    truncated: bool = False


class ProductDetailsData(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    product: Product


type ToolData = ProductSearchData | ProductDetailsData


class ToolResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    tool_call_id: str = Field(min_length=1, max_length=128)
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    status: Literal["ok", "not_found", "not_available", "error"]
    source: ToolSource
    data: ToolData | None = None
    error_code: (
        Literal[
            "unknown_tool",
            "invalid_arguments",
            "timeout",
            "tool_error",
            "invalid_result",
            "result_too_large",
        ]
        | None
    ) = None
