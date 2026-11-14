"""Injectable read-only product access and safe provider failure categories."""

from collections.abc import Sequence
from typing import Protocol

from ai_service.agent.tools.schemas import (
    Product,
    ProductSearchData,
    SearchProductsArgs,
    ToolSource,
)


class ProductProvider(Protocol):
    @property
    def source(self) -> ToolSource:
        """Provenance of the configured provider, not a success guarantee."""
        ...

    async def search_products(
        self, arguments: SearchProductsArgs, *, limit: int
    ) -> Sequence[Product] | ProductSearchData: ...

    async def get_product_details(self, product_id: str) -> Product | None: ...


class ProductProviderUnavailable(Exception):
    """No product integration is configured."""


class InvalidProductPayload(ValueError):
    """The upstream response does not conform to the supported catalog contract."""


class UnsupportedProductFilter(ValueError):
    """A filter cannot be represented faithfully by this provider."""


class BackendProductUnavailable(Exception):
    """Backend transport or HTTP failure, without upstream error text."""


class UnavailableProductProvider:
    source: ToolSource = "unavailable"

    async def search_products(
        self, arguments: SearchProductsArgs, *, limit: int
    ) -> Sequence[Product]:
        raise ProductProviderUnavailable

    async def get_product_details(self, product_id: str) -> Product | None:
        raise ProductProviderUnavailable
