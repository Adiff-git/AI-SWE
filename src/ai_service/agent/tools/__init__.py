"""Typed read-only product tools, with no assumed Backend integration."""

from ai_service.agent.tools.products import create_product_tools
from ai_service.agent.tools.provider import (
    ProductProvider,
    ProductProviderUnavailable,
    UnavailableProductProvider,
)
from ai_service.agent.tools.registry import Tool, ToolRegistry
from ai_service.agent.tools.schemas import (
    Price,
    Product,
    ProductDetailsArgs,
    ProductDetailsData,
    ProductSearchData,
    SearchProductsArgs,
    ToolResult,
)

__all__ = [
    "Price",
    "Product",
    "ProductDetailsArgs",
    "ProductDetailsData",
    "ProductProvider",
    "ProductProviderUnavailable",
    "ProductSearchData",
    "SearchProductsArgs",
    "Tool",
    "ToolRegistry",
    "ToolResult",
    "UnavailableProductProvider",
    "create_product_tools",
]
