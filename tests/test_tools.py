import asyncio
import json
from typing import Literal, cast

import httpx
import pytest
from pydantic import ValidationError

from ai_service.agent.tools import (
    Product,
    ProductDetailsArgs,
    ProductDetailsData,
    SearchProductsArgs,
    Tool,
    ToolRegistry,
    create_product_tools,
)
from ai_service.integrations.llm import ToolCall, ToolFunction


def call(name: str, arguments: object, *, raw: bool = False) -> ToolCall:
    return ToolCall(
        id="call_test",
        function=ToolFunction(
            name=name, arguments=cast(str, arguments) if raw else json.dumps(arguments)
        ),
    )


class FakeProductProvider:
    source: Literal["fake"] = "fake"

    def __init__(self) -> None:
        self.products = [
            Product(
                product_id="TEST-001",
                name="Thiết bị giả lập A",
                category="laptop",
                specifications={"RAM": "16 GB"},
            )
        ]
        self.search_calls: list[tuple[SearchProductsArgs, int]] = []
        self.detail_calls: list[str] = []

    async def search_products(self, arguments: SearchProductsArgs, *, limit: int) -> list[Product]:
        self.search_calls.append((arguments, limit))
        return self.products

    async def get_product_details(self, product_id: str) -> Product | None:
        self.detail_calls.append(product_id)
        return next(
            (
                p
                for p in self.products
                if (p.product_id if isinstance(p, Product) else p["product_id"]) == product_id
            ),
            None,
        )


@pytest.fixture(autouse=True)
def reject_network(monkeypatch: pytest.MonkeyPatch) -> None:
    async def reject(*args: object, **kwargs: object) -> httpx.Response:
        pytest.fail("Product tools must not perform Backend or provider HTTP in tests")

    monkeypatch.setattr(httpx.AsyncClient, "request", reject)
    monkeypatch.setattr(httpx.AsyncClient, "send", reject)


def test_registry_definitions_and_json_schema() -> None:
    registry = create_product_tools()
    assert registry.names() == ("search_products", "get_product_details")
    search, details = registry.definitions()
    assert search.parameters["required"] == ["query"]
    assert search.parameters["additionalProperties"] is False
    assert set(search.parameters["properties"]) == {
        "query",
        "category",
        "min_price",
        "max_price",
        "currency",
    }
    assert details.parameters["required"] == ["product_id"]
    assert details.parameters["additionalProperties"] is False
    search.parameters.clear()
    assert registry.definitions()[0].parameters["type"] == "object"


async def no_result(arguments: ProductDetailsArgs) -> None:
    return None


@pytest.mark.parametrize("name", ["", "invalid name", "https://example.com", "x" * 65])
def test_invalid_registered_name(name: str) -> None:
    with pytest.raises(ValidationError):
        ToolRegistry().register(Tool(name, "Read only", ProductDetailsArgs, no_result, "fake"))


def test_duplicate_and_mutating_tools_are_rejected() -> None:
    registry = create_product_tools()
    with pytest.raises(ValueError, match="Duplicate"):
        registry.register(
            Tool("get_product_details", "Duplicate", ProductDetailsArgs, no_result, "fake")
        )
    with pytest.raises(ValueError, match="read-only"):
        registry.register(
            Tool("delete_cart", "Mutation", ProductDetailsArgs, no_result, "fake", read_only=False)
        )
    with pytest.raises(ValueError, match="fake/unavailable"):
        registry.register(
            Tool("live_catalog", "Not approved", ProductDetailsArgs, no_result, "backend")
        )


def test_fake_search_and_details() -> None:
    provider = FakeProductProvider()
    registry = create_product_tools(provider)
    search = asyncio.run(
        registry.execute(
            call(
                "search_products",
                {
                    "query": "laptop học lập trình",
                    "category": "laptop",
                    "min_price": 0,
                    "max_price": 15_000_000,
                    "currency": "VND",
                },
            )
        )
    )
    assert search.status == "ok"
    assert search.source == "fake"
    assert search.data.products[0].product_id == "TEST-001"
    arguments, limit = provider.search_calls[0]
    assert arguments.max_price == 15_000_000
    assert arguments.currency == "VND"
    assert arguments.category == "laptop"
    assert limit == 5
    details = asyncio.run(registry.execute(call("get_product_details", {"product_id": "TEST-001"})))
    assert details.status == "ok"
    assert details.source == "fake"
    assert details.data.product.specifications == {"RAM": "16 GB"}
    assert details.data.product.price is None
    assert provider.detail_calls == ["TEST-001"]


def test_unavailable_is_not_an_empty_search_or_missing_record() -> None:
    for name, arguments in [
        ("search_products", {"query": "laptop"}),
        ("get_product_details", {"product_id": "TEST-001"}),
    ]:
        result = asyncio.run(create_product_tools().execute(call(name, arguments)))
        assert result.status == "not_available"
        assert result.source == "unavailable"
        assert result.data is None
    provider = FakeProductProvider()
    provider.products = []
    registry = create_product_tools(provider)
    empty = asyncio.run(registry.execute(call("search_products", {"query": "absent"})))
    assert empty.status == "ok"
    assert empty.data.products == []
    missing = asyncio.run(registry.execute(call("get_product_details", {"product_id": "absent"})))
    assert missing.status == "not_found"


@pytest.mark.parametrize(
    "arguments",
    [
        "{bad",
        "[]",
        "null",
        '"text"',
        "true",
        '{"query":"one","query":"two"}',
        '{"query":"x","min_price":NaN}',
        '{"query":"x","max_price":1e999}',
        "{}",
        '{"query":" "}',
        '{"query":123}',
        '{"query":"x","url":"https://bad.example"}',
        '{"query":"x","max_price":-1,"currency":"VND"}',
        '{"query":"x","min_price":2,"max_price":1,"currency":"VND"}',
        '{"query":"x","max_price":15}',
        '{"query":"x","max_price":"15","currency":"VND"}',
        '{"query":"x","max_price":15,"currency":"vnd"}',
        "[" * 1500 + "]" * 1500,
    ],
)
def test_invalid_search_does_not_execute_provider(arguments: str) -> None:
    provider = FakeProductProvider()
    result = asyncio.run(
        create_product_tools(provider).execute(call("search_products", arguments, raw=True))
    )
    assert result.status == "error"
    assert result.error_code == "invalid_arguments"
    assert result.data is None
    assert provider.search_calls == []


@pytest.mark.parametrize("name", ["delete_cart", "pay_order", "run_code", "http_get"])
def test_unknown_tools_never_dispatch(name: str) -> None:
    provider = FakeProductProvider()
    result = asyncio.run(create_product_tools(provider).execute(call(name, {"url": "https://bad"})))
    assert result.error_code == "unknown_tool"
    assert provider.search_calls == provider.detail_calls == []


@pytest.mark.parametrize(
    "arguments",
    [{}, {"product_id": " "}, {"product_id": 123}, {"product_id": "TEST", "url": "https://bad"}],
)
def test_invalid_details_do_not_execute_provider(arguments: dict[str, object]) -> None:
    provider = FakeProductProvider()
    result = asyncio.run(
        create_product_tools(provider).execute(call("get_product_details", arguments))
    )
    assert result.error_code == "invalid_arguments"
    assert provider.detail_calls == []


def test_mismatched_detail_record_is_not_returned() -> None:
    class WrongRecordProvider(FakeProductProvider):
        async def get_product_details(self, product_id: str) -> Product | None:
            return self.products[0]

    result = asyncio.run(
        create_product_tools(WrongRecordProvider()).execute(
            call("get_product_details", {"product_id": "OTHER-ID"})
        )
    )
    assert result.status == "error"
    assert result.data is None


def test_private_fields_removed_and_control_characters_rejected() -> None:
    raw = {
        "product_id": "TEST-001",
        "name": "Thiết bị giả lập",
        "internal_cost": "secret",
        "customer_email": "private",
        "price": {"amount": 100, "currency": "VND", "key": "secret"},
    }
    provider = FakeProductProvider()
    provider.products = [cast(Product, raw)]
    registry = create_product_tools(provider)
    result = asyncio.run(registry.execute(call("get_product_details", {"product_id": "TEST-001"})))
    assert result.status == "ok"
    assert "secret" not in result.model_dump_json()
    assert "private" not in result.model_dump_json()
    raw["name"] = "Injected\x00control"
    invalid = asyncio.run(registry.execute(call("get_product_details", {"product_id": "TEST-001"})))
    assert invalid.error_code == "invalid_result"


def test_search_and_result_size_bounds() -> None:
    provider = FakeProductProvider()
    provider.products *= 7
    registry = create_product_tools(provider)
    result = asyncio.run(registry.execute(call("search_products", {"query": "laptop"})))
    assert len(result.data.products) == 5
    assert result.data.truncated is True
    provider.products = [
        Product(
            product_id="TEST-001",
            name="Giả lập",
            specifications={f"spec{i}": "ệ" * 200 for i in range(10)},
        )
    ]
    oversized = asyncio.run(
        registry.execute(call("get_product_details", {"product_id": "TEST-001"}))
    )
    assert oversized.status == "ok"
    provider.products *= 5
    oversized = asyncio.run(registry.execute(call("search_products", {"query": "laptop"})))
    assert oversized.error_code == "result_too_large"
    assert len(oversized.model_dump_json().encode("utf-8")) <= 8192


def test_tool_error_is_sanitized(caplog: pytest.LogCaptureFixture) -> None:
    async def fail(arguments: ProductDetailsArgs) -> ProductDetailsData:
        raise RuntimeError("private-api-key internal traceback")

    registry = ToolRegistry()
    registry.register(Tool("test_failure", "Fake failure", ProductDetailsArgs, fail, "fake"))
    result = asyncio.run(registry.execute(call("test_failure", {"product_id": "TEST"})))
    assert result.error_code == "tool_error"
    assert "private-api-key" not in result.model_dump_json()
    assert "private-api-key" not in caplog.text


def test_timeout_cancels_tool() -> None:
    cancelled = []

    async def wait(arguments: ProductDetailsArgs) -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    registry = ToolRegistry(timeout=0.01)
    registry.register(Tool("test_timeout", "Fake timeout", ProductDetailsArgs, wait, "fake"))
    result = asyncio.run(registry.execute(call("test_timeout", {"product_id": "TEST"})))
    assert result.error_code == "timeout"
    assert cancelled == [True]


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_timeout(timeout: float) -> None:
    with pytest.raises(ValueError):
        ToolRegistry(timeout=timeout)
