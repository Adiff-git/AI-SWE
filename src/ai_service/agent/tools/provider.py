"""Injectable product access; no Backend paths or network I/O are assumed."""

from collections.abc import Sequence
from typing import Protocol

from ai_service.agent.tools.schemas import Product, SearchProductsArgs, ToolSource


class ProductProvider(Protocol):
    @property
    def source(self) -> ToolSource:
        """Current sources are explicitly fake or unavailable, never live Backend."""
        ...

    async def search_products(
        self, arguments: SearchProductsArgs, *, limit: int
    ) -> Sequence[Product]: ...

    async def get_product_details(self, product_id: str) -> Product | None: ...


class ProductProviderUnavailable(Exception):
    """No approved product integration is available."""


class UnavailableProductProvider:
    source: ToolSource = "unavailable"

    async def search_products(
        self, arguments: SearchProductsArgs, *, limit: int
    ) -> Sequence[Product]:
        raise ProductProviderUnavailable

    async def get_product_details(self, product_id: str) -> Product | None:
        raise ProductProviderUnavailable
