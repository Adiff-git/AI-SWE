"""Adapter for Backend-SWE's public, published-product catalog (SWE-165).

Wire DTOs intentionally differ from the unapproved SWE-69 internal-API proposal.
Only fixed GET paths use the injected, application-owned HTTPX pool.
"""

import json
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

import httpx
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, model_validator

from ai_service.agent.tools.provider import (
    BackendProductUnavailable,
    InvalidProductPayload,
    UnsupportedProductFilter,
)
from ai_service.agent.tools.schemas import (
    ImageURL,
    Price,
    Product,
    ProductSearchData,
    ProductVariant,
    SearchProductsArgs,
    ShortText,
)
from ai_service.integrations.backend_client import (
    BackendResponseTooLarge,
    read_backend_response,
)

type CatalogID = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
]
_CATALOG_ID = TypeAdapter(CatalogID)
_SHORT_TEXT = TypeAdapter(ShortText)
type SpecificationKey = Annotated[
    str, StringConstraints(max_length=128, pattern=r"^[a-z][a-z0-9_]*$")
]


class _WireDTO(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")


class _Category(_WireDTO):
    id: CatalogID
    name: ShortText


class _Price(_WireDTO):
    amount: int = Field(ge=0, lt=10**30)
    currency: Literal["VND"]

    def product_price(self) -> Price:
        return Price(amount=Decimal(self.amount), currency=self.currency)


class _Summary(_WireDTO):
    id: CatalogID
    name: ShortText
    category: _Category
    primaryImageUrl: ImageURL | None

    def product_fields(self) -> dict[str, Any]:
        return {
            "product_id": self.id,
            "name": self.name,
            "category": self.category.id,
            "category_name": self.category.name,
            "primary_image_url": self.primaryImageUrl,
        }


class _Listing(_Summary):
    displayPrice: _Price | None
    representativeVariantId: CatalogID | None

    @model_validator(mode="after")
    def paired_price(self) -> Self:
        if (self.displayPrice is None) != (self.representativeVariantId is None):
            raise ValueError("Unpaired listing price")
        return self


class _Page(_WireDTO):
    items: list[_Listing]
    page: int = Field(ge=0, le=2**31 - 1)
    size: int = Field(ge=1, le=100)
    totalItems: int = Field(ge=0, le=2**63 - 1)
    totalPages: int = Field(ge=0, le=2**31 - 1)


class _Specifications(_WireDTO):
    schema_version: int = Field(ge=1, le=1)
    values: dict[SpecificationKey, Any]

    def texts(self) -> tuple[dict[str, str], bool]:
        # Validate every value, even those outside the bounded model projection.
        values = {
            key: _SHORT_TEXT.validate_python(_specification_text(value))
            for key, value in self.values.items()
        }
        return dict(list(values.items())[:10]), len(values) > 10


def _specification_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal) and value.is_finite():
        # A short JSON exponent can otherwise expand into gigabytes before the
        # bounded text schema gets a chance to reject it.
        if value.adjusted() > 199 or value.as_tuple().exponent < -199:
            raise InvalidProductPayload
        return format(value, "f")
    if (
        isinstance(value, dict)
        and set(value) == {"value", "unit"}
        and type(value["value"]) in (int, Decimal)
        and isinstance(value["unit"], str)
        and value["unit"].strip()
    ):
        return f"{_specification_text(value['value'])} {value['unit']}"
    raise InvalidProductPayload


class _Variant(_WireDTO):
    id: CatalogID
    sku: ShortText
    options: dict[str, str]
    sellingPrice: _Price
    technicalSpecifications: _Specifications

    def product_variant(self) -> ProductVariant:
        specifications, truncated = self.technicalSpecifications.texts()
        return ProductVariant(
            variant_id=self.id,
            sku=self.sku,
            options=self.options,
            price=self.sellingPrice.product_price(),
            specifications=specifications,
            specifications_truncated=truncated,
        )


class _Image(_WireDTO):
    id: CatalogID
    url: ImageURL


class _Detail(_Summary):
    variants: list[_Variant] = Field(min_length=1)
    images: list[_Image]


def _reject_constant(value: str) -> None:
    raise InvalidProductPayload


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidProductPayload
        result[key] = value
    return result


def _json(body: bytes) -> Any:
    try:
        return json.loads(
            body, parse_float=Decimal, parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (ValueError, RecursionError):
        raise InvalidProductPayload from None


def _catalog_id(value: str) -> str:
    # No normalization: Backend requires canonical lowercase UUIDs. Validate
    # before building a path, preventing traversal, query or host selection.
    try:
        return _CATALOG_ID.validate_python(value)
    except ValueError:
        raise UnsupportedProductFilter from None


class BackendProductProvider:
    source: Literal["backend"] = "backend"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def _read(
        self, path: str, *, params: dict[str, str | int] | None = None, missing: bool = False
    ) -> Any:
        try:
            async with self._client.stream("GET", path, params=params) as response:
                body = await read_backend_response(response)
                # Also support injected HTTPX clients without the shared status hook.
                if response.status_code == 404 and missing:
                    return self._missing(body, path)
                response.raise_for_status()
                if response.status_code != 200:
                    raise InvalidProductPayload
                return _json(body)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404 and missing:
                return self._missing(exc.response.content, path)
            raise BackendProductUnavailable from None
        except httpx.TimeoutException:
            raise TimeoutError from None
        except httpx.RequestError:
            raise BackendProductUnavailable from None
        except BackendResponseTooLarge:
            raise InvalidProductPayload from None

    @staticmethod
    def _missing(body: bytes, path: str) -> None:
        payload = _json(body)
        # Actual Backend ProblemDetail, not the draft PRODUCT_NOT_FOUND envelope.
        if (
            not isinstance(payload, dict)
            or payload.get("status") != 404
            or payload.get("detail") != "Product not found"
            or payload.get("instance") != path
        ):
            raise InvalidProductPayload
        return None

    async def search_products(
        self, arguments: SearchProductsArgs, *, limit: int
    ) -> ProductSearchData:
        if not 1 <= limit <= 5:
            raise UnsupportedProductFilter
        if arguments.currency not in (None, "VND"):
            raise UnsupportedProductFilter
        params: dict[str, str | int] = {"q": arguments.query, "page": 0, "size": limit}
        if arguments.category is not None:
            params["categoryId"] = _catalog_id(arguments.category)
        for name, value in [("minPrice", arguments.min_price), ("maxPrice", arguments.max_price)]:
            if value is not None:
                if value != value.to_integral_value():
                    raise UnsupportedProductFilter
                params[name] = format(value, ".0f")
        page = _Page.model_validate(await self._read("/api/products", params=params))
        if (
            page.page != 0 or page.size != limit or len(page.items) > limit
            or len(page.items) > page.totalItems
            or page.totalPages != min(2**31 - 1, (page.totalItems + limit - 1) // limit)
            or len({item.id for item in page.items}) != len(page.items)
        ):
            raise InvalidProductPayload
        return ProductSearchData(
            products=[
                Product(
                    **item.product_fields(),
                    price=item.displayPrice.product_price() if item.displayPrice else None,
                    representative_variant_id=item.representativeVariantId,
                )
                for item in page.items
            ],
            # Publication rechecks can shorten a page; do not invent a sentinel
            # product or automatically traverse subsequent pages.
            truncated=page.totalItems > len(page.items),
        )

    async def get_product_details(self, product_id: str) -> Product | None:
        path = f"/api/products/{_catalog_id(product_id)}"
        payload = await self._read(path, missing=True)
        if payload is None:
            return None
        detail = _Detail.model_validate(payload)
        if detail.id != product_id or len({v.id for v in detail.variants}) != len(detail.variants):
            raise InvalidProductPayload
        variants = [variant.product_variant() for variant in detail.variants]
        single = variants[0] if len(variants) == 1 else None
        return Product(
            **detail.product_fields(),
            # Multiple variants have no single authoritative product price/spec.
            price=single.price if single else None,
            representative_variant_id=single.variant_id if single else None,
            specifications=single.specifications if single else {},
            specifications_truncated=single.specifications_truncated if single else False,
            variants=variants[:5], variants_truncated=len(variants) > 5,
            images=[image.url for image in detail.images[:5]],
            images_truncated=len(detail.images) > 5,
        )
