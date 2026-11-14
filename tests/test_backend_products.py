"""Synthetic Backend DTO fixtures; all HTTP passes through MockTransport."""

import asyncio
import copy
import gzip
import json
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError

from ai_service.agent.conversation import (
    CATALOG_NOTICE,
    PARTIAL_CATALOG_NOTICE,
    VERIFIED_CATALOG_NOTICE,
    AgentTurn,
)
from ai_service.agent.orchestrator import ShoppingAgent
from ai_service.agent.tools import BackendProductProvider, Price, create_product_tools
from ai_service.core.config import Settings
from ai_service.integrations.backend_client import create_backend_client
from ai_service.integrations.llm import OpenAICompatibleLLMClient, ToolCall, ToolFunction

PRODUCT_ID = "11111111-1111-1111-1111-111111111111"
OTHER_ID = "22222222-2222-2222-2222-222222222222"
CATEGORY_ID = "33333333-3333-3333-3333-333333333333"
VARIANT_ID = "44444444-4444-4444-4444-444444444444"
IMAGE_ID = "55555555-5555-5555-5555-555555555555"
IMAGE_URL = "https://images.example/product.webp?signature=synthetic"
LARGE_AMOUNT = 123456789012345678901234567890


def listing(*, priced=True):
    return {
        "id": PRODUCT_ID,
        "name": "Laptop mẫu A",
        "category": {"id": CATEGORY_ID, "name": "Laptop"},
        "primaryImageUrl": IMAGE_URL,
        "displayPrice": {"amount": LARGE_AMOUNT, "currency": "VND"} if priced else None,
        "representativeVariantId": VARIANT_ID if priced else None,
        "internal_cost": "PRIVATE",
    }


def page(items=None, *, total=1):
    return {
        "items": [listing()] if items is None else items,
        "page": 0, "size": 5, "totalItems": total, "totalPages": (total + 4) // 5,
    }


def detail():
    product = listing()
    del product["displayPrice"], product["representativeVariantId"]
    product.update({
        "description": "Not selected for the model",
        "brand": {"id": OTHER_ID, "code": "sample", "name": "Sample"},
        "variants": [{
            "id": VARIANT_ID, "sku": "SAMPLE-16", "options": {"RAM": "16 GB"},
            "sellingPrice": {"amount": LARGE_AMOUNT, "currency": "VND"},
            "technicalSpecifications": {
                "schema_version": 1,
                "values": {
                    "ram": {"value": 16, "unit": "GB"},
                    "screen": {"value": 13.25, "unit": "inch"},
                    "storage_type": "SSD", "cores": 8, "touchscreen": False,
                },
            },
            "supplier_secret": "PRIVATE",
        }],
        "images": [{
            "id": IMAGE_ID, "url": IMAGE_URL, "altText": "Ảnh mẫu", "width": 100,
            "height": 100, "displayOrder": 0, "isPrimary": True,
        }],
    })
    return product


def call(name="search_products", arguments=None, *, raw=None):
    return ToolCall(id="lookup", function=ToolFunction(
        name=name, arguments=raw if raw is not None else json.dumps(
            arguments if arguments is not None else {"query": "laptop"}
        ),
    ))


def run_tool(handler, tool_call=None, *, timeout=5):
    async def run():
        settings = Settings(_env_file=None, backend_api_base_url="https://backend.example")
        async with create_backend_client(
            settings, transport=httpx.MockTransport(handler)
        ) as client:
            registry = create_product_tools(BackendProductProvider(client), timeout=timeout)
            result = await registry.execute(tool_call or call())
            assert not client.is_closed  # Provider never owns or replaces the shared pool.
            return result
    return asyncio.run(run())


def test_search_maps_real_parameters_money_category_images_and_provenance():
    requests = []

    def backend(request):
        requests.append(request)
        assert request.method == "GET" and request.url.path == "/api/products"
        assert request.content == b""
        assert dict(request.url.params) == {
            "q": "máy tính & học", "page": "0", "size": "5", "categoryId": CATEGORY_ID,
            "minPrice": "100", "maxPrice": "999999999999999",
        }
        return httpx.Response(200, json=page())

    result = run_tool(backend, call(arguments={
        "query": "máy tính & học", "category": CATEGORY_ID, "min_price": "100.00",
        "max_price": "999999999999999", "currency": "VND",
    }))
    assert result.status == "ok" and result.source == "backend"
    product = result.data.products[0]
    assert product.category == CATEGORY_ID and product.category_name == "Laptop"
    assert product.price.amount == Decimal(LARGE_AMOUNT)
    assert json.loads(result.model_dump_json())["data"]["products"][0]["price"]["amount"] == str(
        LARGE_AMOUNT
    )
    assert product.representative_variant_id == VARIANT_ID
    assert product.primary_image_url == IMAGE_URL
    assert "PRIVATE" not in result.model_dump_json()
    assert len(requests) == 1


@pytest.mark.parametrize(("items", "total", "truncated"), [([], 0, False), ([], 6, True)])
def test_empty_search_and_backend_pagination(items, total, truncated):
    result = run_tool(lambda _: httpx.Response(200, json=page(items, total=total)))
    assert result.status == "ok"
    assert result.data.products == []
    assert result.data.truncated is truncated


def test_listing_without_price_is_not_free():
    result = run_tool(lambda _: httpx.Response(200, json=page([listing(priced=False)])))
    product = result.data.products[0]
    assert product.price is None and product.representative_variant_id is None


def test_details_preserve_exact_variant_specs_and_images():
    def backend(request):
        assert request.method == "GET" and request.url.path == f"/api/products/{PRODUCT_ID}"
        return httpx.Response(200, json=detail())

    result = run_tool(backend, call("get_product_details", {"product_id": PRODUCT_ID}))
    assert result.status == "ok" and result.source == "backend"
    product = result.data.product
    variant = product.variants[0]
    assert variant.variant_id == VARIANT_ID and variant.sku == "SAMPLE-16"
    assert variant.options == {"RAM": "16 GB"}
    assert variant.price.amount == product.price.amount == Decimal(LARGE_AMOUNT)
    assert product.specifications == variant.specifications == {
        "ram": "16 GB", "screen": "13.25 inch", "storage_type": "SSD",
        "cores": "8", "touchscreen": "false",
    }
    assert product.images == [IMAGE_URL] and product.primary_image_url == IMAGE_URL
    assert "PRIVATE" not in result.model_dump_json()
    assert "Not selected" not in result.model_dump_json()


def test_multiple_variants_are_not_flattened_to_an_arbitrary_product_price():
    payload = detail()
    other = copy.deepcopy(payload["variants"][0])
    other["id"] = OTHER_ID
    other["sellingPrice"]["amount"] = 100
    other["technicalSpecifications"]["values"]["ram"]["value"] = 32
    payload["variants"].append(other)
    result = run_tool(lambda _: httpx.Response(200, json=payload),
                      call("get_product_details", {"product_id": PRODUCT_ID}))
    product = result.data.product
    assert product.price is None and product.specifications == {}
    assert product.representative_variant_id is None
    assert [v.specifications["ram"] for v in product.variants] == ["16 GB", "32 GB"]
    assert [v.price.amount for v in product.variants] == [Decimal(LARGE_AMOUNT), Decimal(100)]


def test_bounded_details_explicitly_report_omitted_fields():
    payload = detail()
    payload["variants"][0]["technicalSpecifications"]["values"] = {
        f"spec_{i}": i for i in range(11)
    }
    payload["variants"] = [
        {**payload["variants"][0], "id": f"{i:08x}-1111-1111-1111-111111111111"}
        for i in range(6)
    ]
    payload["images"] *= 6
    result = run_tool(lambda _: httpx.Response(200, json=payload),
                      call("get_product_details", {"product_id": PRODUCT_ID}))
    product = result.data.product
    assert len(product.variants) == len(product.images) == 5
    assert product.variants_truncated and product.images_truncated
    assert all(v.specifications_truncated and len(v.specifications) == 10 for v in product.variants)


@pytest.mark.parametrize("arguments", [
    {"query": "x", "currency": "USD"},
    {"query": "x", "min_price": "10.01", "currency": "VND"},
    {"query": "x", "category": "laptops"},
])
def test_unsupported_filters_are_never_silently_ignored(arguments):
    def backend(_):
        pytest.fail("Unsupported filters must fail before making a request")
    result = run_tool(backend, call(arguments=arguments))
    assert result.error_code == "unsupported_filter" and result.data is None


@pytest.mark.parametrize("identifier", [
    "../orders", "https://bad.example", "?x=1", "ID", PRODUCT_ID.replace("1", "A"),
])
def test_product_path_is_not_model_controlled(identifier):
    def backend(_):
        pytest.fail("Invalid identifiers must never reach HTTP")
    result = run_tool(backend, call("get_product_details", {"product_id": identifier}))
    assert result.error_code == "unsupported_filter"


def test_exact_json_price_filters_do_not_pass_through_float():
    def backend(request):
        assert request.url.params["maxPrice"] == "999999999999999"
        return httpx.Response(200, json=page([], total=0))
    result = run_tool(backend, call(raw=(
        '{"query":"x","max_price":999999999999999.0000000000000000,"currency":"VND"}'
    )))
    assert result.status == "ok"
    with pytest.raises(ValidationError):
        Price(amount=0.1, currency="VND")


def test_tiny_vnd_fraction_is_not_rounded_into_a_valid_filter():
    def backend(_):
        pytest.fail("Fractional VND must not be rounded or sent to Backend")
    result = run_tool(backend, call(raw=(
        '{"query":"x","max_price":10.00000000000000001,"currency":"VND"}'
    )))
    assert result.error_code == "unsupported_filter"


@pytest.mark.parametrize("status", [301, 401, 403, 404, 422, 429, 500, 503])
def test_http_failures_are_sanitized_and_not_empty_results(status, caplog):
    requests = []

    def backend(request):
        requests.append(request)
        return httpx.Response(status, text="PRIVATE upstream detail", headers={
            "Location": "https://other.example/secret",
        })
    result = run_tool(backend)
    assert result.status == "error" and result.error_code == "backend_unavailable"
    assert result.source == "backend" and result.data is None
    assert "PRIVATE" not in result.model_dump_json() + caplog.text
    assert len(requests) == 1  # Neither retries nor redirects.


def test_only_actual_backend_product_404_is_not_found():
    path = f"/api/products/{PRODUCT_ID}"
    result = run_tool(lambda _: httpx.Response(404, json={
        "type": "about:blank", "title": "Not Found", "status": 404,
        "detail": "Product not found", "instance": path,
        "message": "Product not found", "path": path, "timestamp": "2026-11-14T00:00:00Z",
        "fieldErrors": {},
    }), call("get_product_details", {"product_id": PRODUCT_ID}))
    assert result.status == "not_found" and result.data is None


def test_compressed_product_404_is_decoded_once_by_shared_client():
    body = json.dumps({
        "status": 404, "detail": "Product not found", "instance": f"/api/products/{PRODUCT_ID}",
    }).encode()
    result = run_tool(lambda _: httpx.Response(
        404, content=gzip.compress(body), headers={"Content-Encoding": "gzip"},
    ), call("get_product_details", {"product_id": PRODUCT_ID}))
    assert result.status == "not_found"


@pytest.mark.parametrize("body", [
    b"<html>Not found</html>", b'{}', b'{"status":404,"detail":"No route"}',
])
def test_proxy_and_unknown_404_are_invalid_results(body):
    result = run_tool(lambda _: httpx.Response(404, content=body),
                      call("get_product_details", {"product_id": PRODUCT_ID}))
    assert result.error_code == "invalid_result" and result.data is None


@pytest.mark.parametrize(("exception", "code"), [
    (httpx.ConnectError, "backend_unavailable"), (httpx.ReadTimeout, "timeout"),
    (httpx.ConnectTimeout, "timeout"), (httpx.PoolTimeout, "timeout"),
])
def test_network_and_httpx_timeout_mapping(exception, code):
    def backend(request):
        raise exception("PRIVATE URL and credentials", request=request)
    result = run_tool(backend)
    assert result.error_code == code and result.data is None
    assert "PRIVATE" not in result.model_dump_json()


def test_tool_deadline_cancels_backend_read():
    cancelled = []

    async def backend(_):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)
    result = run_tool(backend, timeout=0.01)
    assert result.error_code == "timeout" and cancelled == [True]


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(id=OTHER_ID),
    lambda p: p.pop("category"),
    lambda p: p.update(name="bad\x00name"),
    lambda p: p.update(primaryImageUrl="file:///etc/passwd"),
    lambda p: p.update(variants=[]),
    lambda p: p["variants"].append(copy.deepcopy(p["variants"][0])),
    lambda p: p["variants"][0]["sellingPrice"].update(amount=1.5),
    lambda p: p["variants"][0]["sellingPrice"].update(amount="123"),
    lambda p: p["variants"][0]["sellingPrice"].update(amount=True),
    lambda p: p["variants"][0]["sellingPrice"].update(currency="USD"),
    lambda p: p["variants"][0]["technicalSpecifications"].update(schema_version=2),
    lambda p: p["variants"][0]["technicalSpecifications"].update(values={"bad": [1, 2]}),
])
def test_invalid_detail_payload_never_exposes_product_data(mutate):
    payload = detail()
    mutate(payload)
    result = run_tool(lambda _: httpx.Response(200, json=payload),
                      call("get_product_details", {"product_id": PRODUCT_ID}))
    assert result.error_code == "invalid_result" and result.data is None


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(page=1), lambda p: p.update(size=20),
    lambda p: p.update(totalPages=5), lambda p: p.update(totalItems=0),
    lambda p: p.update(items=p["items"] * 6),
    lambda p: p["items"][0].update(representativeVariantId=None),
])
def test_invalid_search_metadata_and_price_pairing(mutate):
    payload = page()
    mutate(payload)
    result = run_tool(lambda _: httpx.Response(200, json=payload))
    assert result.error_code == "invalid_result" and result.data is None


@pytest.mark.parametrize("body", [b"not json", b'[]', b'{"items":[],"items":[]}',
                                        b'{"items":NaN}', b"x" * 65_537])
def test_invalid_json_or_oversized_backend_body(body):
    result = run_tool(lambda _: httpx.Response(200, content=body))
    assert result.error_code == "invalid_result" and result.data is None


@pytest.mark.parametrize("number", ["1e999999999", "1e-999999999"])
def test_spec_number_cannot_expand_beyond_text_budget(number):
    payload = detail()
    payload["variants"][0]["technicalSpecifications"]["values"] = {"ram": "NUMBER"}
    body = json.dumps(payload).replace('"NUMBER"', number).encode()
    result = run_tool(lambda _: httpx.Response(200, content=body),
                      call("get_product_details", {"product_id": PRODUCT_ID}))
    assert result.error_code == "invalid_result" and result.data is None


@pytest.mark.parametrize("status", [200, 404])
def test_streaming_body_limit_stops_read_and_closes_response(status):
    class Body(httpx.AsyncByteStream):
        chunks = 0
        closed = False

        async def __aiter__(self):
            for _ in range(20):
                self.chunks += 1
                yield b" " * 8192

        async def aclose(self):
            self.closed = True

    body = Body()
    result = run_tool(lambda _: httpx.Response(status, stream=body))
    assert result.error_code == "invalid_result"
    assert body.chunks == 9 and body.closed


def test_backend_data_still_respects_existing_tool_result_budget():
    items = [
        {**listing(), "id": f"{i:08x}-1111-1111-1111-111111111111",
         "primaryImageUrl": "https://images.example/" + "x" * 1950}
        for i in range(5)
    ]
    result = run_tool(lambda _: httpx.Response(200, json=page(items, total=5)))
    assert result.error_code == "result_too_large" and result.data is None
    assert len(result.model_dump_json().encode()) <= 8192


def test_absent_images_and_empty_specs_do_not_create_facts():
    payload = detail()
    payload["primaryImageUrl"] = None
    payload["images"] = []
    payload["variants"][0]["technicalSpecifications"]["values"] = {}
    result = run_tool(lambda _: httpx.Response(200, json=payload),
                      call("get_product_details", {"product_id": PRODUCT_ID}))
    product = result.data.product
    assert product.primary_image_url is None and product.images == []
    assert product.specifications == product.variants[0].specifications == {}
    assert not hasattr(product, "availability")


def test_lifespan_wires_existing_agent(client):
    assert isinstance(client.app.state.shopping_agent, ShoppingAgent)
    assert not client.app.state.backend_client.is_closed


def tool_reply(*ids):
    return {"model": "mock", "choices": [{"finish_reason": "tool_calls", "message": {
        "role": "assistant", "content": None, "tool_calls": [{
            "id": f"lookup_{i}", "type": "function", "function": {
                "name": "get_product_details", "arguments": json.dumps({"product_id": identifier}),
            },
        } for i, identifier in enumerate(ids)],
    }}]}


def text_reply():
    return {"model": "mock", "choices": [{"finish_reason": "stop", "message": {
        "role": "assistant", "content": "So sánh theo thông số từ Backend.",
    }}]}


def agent_roundtrip(*, failed_second=False, no_lookup=False):
    backend_requests, llm_requests = [], []

    def backend(request):
        backend_requests.append(request)
        payload = detail()
        if request.url.path.endswith(OTHER_ID):
            if failed_second:
                raise httpx.ReadTimeout("PRIVATE", request=request)
            payload["id"] = OTHER_ID
            payload["name"] = "Laptop mẫu B"
        return httpx.Response(200, json=payload)

    def llm_http(request):
        llm_requests.append(json.loads(request.content))
        reply = text_reply() if no_lookup or len(llm_requests) > 1 else tool_reply(
            PRODUCT_ID, OTHER_ID
        )
        return httpx.Response(200, json=reply)

    async def run():
        settings = Settings(_env_file=None, backend_api_base_url="https://backend.example",
                            llm_api_key="synthetic", llm_base_url="https://llm.example/v1",
                            llm_model="mock")
        async with (
            create_backend_client(settings, transport=httpx.MockTransport(backend)) as client,
            httpx.AsyncClient(transport=httpx.MockTransport(llm_http)) as llm_client,
        ):
            llm = OpenAICompatibleLLMClient(settings, llm_client)
            agent = ShoppingAgent(llm, tools=create_product_tools(BackendProductProvider(client)))
            first = await agent.respond(AgentTurn(message="So sánh hai laptop này"))
            second = await agent.respond(AgentTurn(message="Lời khuyên chung"))
            return first, second
    first, second = asyncio.run(run())
    assert second.catalog_verified is False and second.catalog_evidence == ()
    assert second.answer.startswith(CATALOG_NOTICE)
    return first, backend_requests, llm_requests


def test_comparison_uses_existing_detail_tools_and_verified_backend_evidence():
    result, backend_requests, llm_requests = agent_roundtrip()
    assert result.catalog_verified and result.answer.startswith(VERIFIED_CATALOG_NOTICE)
    assert len(result.catalog_evidence) == len(backend_requests) == 2
    assert [r.data.product.product_id for r in result.catalog_evidence] == [PRODUCT_ID, OTHER_ID]
    messages = llm_requests[1]["messages"]
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "tool", "tool"]
    assert "source=backend" in messages[0]["content"]
    assert "Chưa có kết nối Backend thật" not in messages[0]["content"]
    assert all(json.loads(m["content"])["source"] == "backend" for m in messages[-2:])
    assert len(llm_requests[0]["tools"]) == 2  # No comparison/mutation tool.


def test_one_success_does_not_certify_failed_comparison():
    result, requests, _ = agent_roundtrip(failed_second=True)
    assert result.catalog_verified is False
    assert result.answer.startswith(PARTIAL_CATALOG_NOTICE)
    assert [r.status for r in result.catalog_evidence] == ["ok", "error"]
    assert result.catalog_evidence[-1].error_code == "timeout" and len(requests) == 2


def test_backend_capability_alone_does_not_verify_no_tool_answer():
    result, requests, _ = agent_roundtrip(no_lookup=True)
    assert result.catalog_verified is False and not requests
    assert result.catalog_evidence == ()
