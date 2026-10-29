"""Two read-only definitions backed by an explicitly injected product provider."""

from collections.abc import Sequence

from ai_service.agent.tools.provider import ProductProvider, UnavailableProductProvider
from ai_service.agent.tools.registry import Tool, ToolRegistry
from ai_service.agent.tools.schemas import (
    Product,
    ProductDetailsArgs,
    ProductDetailsData,
    ProductSearchData,
    SearchProductsArgs,
)


def _product(value: Product) -> Product:
    return Product.model_validate(
        value.model_dump(warnings=False) if isinstance(value, Product) else value
    )


def create_product_tools(
    provider: ProductProvider | None = None, *, timeout: float = 5
) -> ToolRegistry:
    provider = provider if provider is not None else UnavailableProductProvider()
    registry = ToolRegistry(timeout=timeout)

    async def search(arguments: SearchProductsArgs) -> ProductSearchData:
        products = await provider.search_products(arguments, limit=5)
        if not isinstance(products, Sequence) or isinstance(products, (str, bytes)):
            raise ValueError("Invalid product search result")
        return ProductSearchData(
            products=[_product(product) for product in products[:5]], truncated=len(products) > 5
        )

    async def details(arguments: ProductDetailsArgs) -> ProductDetailsData | None:
        product = await provider.get_product_details(arguments.product_id)
        if product is None:
            return None
        validated = _product(product)
        if validated.product_id != arguments.product_id:
            raise ValueError("Product identifier mismatch")
        return ProductDetailsData(product=validated)

    registry.register(
        Tool(
            name="search_products",
            description=(
                "Tìm sản phẩm theo nhu cầu và bộ lọc giá có tiền tệ rõ ràng. "
                "Nguồn hiện tại chỉ là fake hoặc chưa khả dụng, không phải catalog thật."
            ),
            arguments=SearchProductsArgs,
            handler=search,
            source=provider.source,
        )
    )
    registry.register(
        Tool(
            name="get_product_details",
            description=(
                "Đọc thông tin sản phẩm theo ID; không thay đổi dữ liệu. "
                "Không suy diễn giá, tồn kho hay bảo hành nếu kết quả không cung cấp."
            ),
            arguments=ProductDetailsArgs,
            handler=details,
            source=provider.source,
        )
    )
    return registry
