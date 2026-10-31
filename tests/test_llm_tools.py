import asyncio
import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import ValidationError

from ai_service.agent.tools import create_product_tools
from ai_service.core.config import Settings
from ai_service.integrations.llm import (
    LLMConfigurationError,
    LLMMessage,
    LLMProviderError,
    LLMResponseError,
    LLMTimeoutError,
    ToolAssistantMessage,
    ToolLLMResponse,
    ToolResultMessage,
    create_llm_client,
)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        llm_api_key="fake-key",
        llm_base_url="https://provider.example/v1",
        llm_model="fake-model",
        llm_timeout=2,
    )


def tool_completion() -> dict[str, object]:
    return {
        "model": "fake-model",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_test",
                            "type": "function",
                            "function": {
                                "name": "search_products",
                                "arguments": '{"query":"laptop"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
    }


def invoke(
    settings: Settings, handler: Callable[[httpx.Request], httpx.Response]
) -> ToolLLMResponse:
    async def run() -> ToolLLMResponse:
        async with create_llm_client(settings, transport=httpx.MockTransport(handler)) as client:
            return await client.complete_with_tools(
                [LLMMessage(role="user", content="Tư vấn laptop")],
                create_product_tools().definitions(),
            )

    return asyncio.run(run())


def test_adapter_tool_call_result_round_trip(settings: Settings) -> None:
    requests = []
    registry = create_product_tools()

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        assert payload["model"] == "fake-model"
        assert payload["stream"] is False
        assert payload["parallel_tool_calls"] is False
        assert payload["tools"][0]["type"] == "function"
        assert payload["tools"][0]["function"]["name"] == "search_products"
        assert payload["tools"][0]["function"]["parameters"]["additionalProperties"] is False
        if len(requests) == 1:
            assert payload["tool_choice"] == "auto"
            return httpx.Response(200, json=tool_completion())
        assert payload["tool_choice"] == "none"
        assert [m["role"] for m in payload["messages"]] == ["user", "assistant", "tool"]
        assert payload["messages"][1]["tool_calls"][0]["id"] == "call_test"
        assert payload["messages"][2]["tool_call_id"] == "call_test"
        assert json.loads(payload["messages"][2]["content"])["status"] == "not_available"
        return httpx.Response(
            200,
            json={
                "model": "fake-model",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Chưa thể kiểm tra catalog."},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    async def run() -> None:
        messages = [LLMMessage(role="user", content="Tư vấn laptop")]
        async with create_llm_client(settings, transport=httpx.MockTransport(handler)) as client:
            first = await client.complete_with_tools(messages, registry.definitions())
            assert first.message.content is None
            call = first.message.tool_calls[0]
            result = await registry.execute(call)
            final = await client.complete_with_tools(
                [
                    *messages,
                    first.message,
                    ToolResultMessage(tool_call_id=call.id, content=result.model_dump_json()),
                ],
                registry.definitions(),
                tool_choice="none",
            )
            assert final.message.content == "Chưa thể kiểm tra catalog."
            assert final.message.tool_calls == []

    asyncio.run(run())
    assert len(requests) == 2


@pytest.mark.parametrize(
    "change",
    [
        "missing_id",
        "blank_id",
        "duplicate_id",
        "missing_role",
        "wrong_role",
        "wrong_type",
        "nonstring_arguments",
        "large_arguments",
        "large_utf8_arguments",
        "missing_function",
    ],
)
def test_malformed_tool_response(settings: Settings, change: str) -> None:
    payload = tool_completion()
    message = payload["choices"][0]["message"]
    call = message["tool_calls"][0]
    if change == "missing_id":
        del call["id"]
    elif change == "blank_id":
        call["id"] = " "
    elif change == "duplicate_id":
        message["tool_calls"].append(call.copy())
    elif change == "missing_role":
        del message["role"]
    elif change == "wrong_role":
        message["role"] = "user"
    elif change == "wrong_type":
        call["type"] = "code"
    elif change == "nonstring_arguments":
        call["function"]["arguments"] = {"query": "laptop"}
    elif change == "large_arguments":
        call["function"]["arguments"] = "x" * 4097
    elif change == "large_utf8_arguments":
        call["function"]["arguments"] = "ệ" * 2000
    else:
        del call["function"]
    with pytest.raises(LLMResponseError):
        invoke(settings, lambda request: httpx.Response(200, json=payload))


def test_invalid_argument_json_reaches_dispatcher(settings: Settings) -> None:
    payload = tool_completion()
    payload["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = "{bad JSON"
    reply = invoke(settings, lambda request: httpx.Response(200, json=payload))
    result = asyncio.run(create_product_tools().execute(reply.message.tool_calls[0]))
    assert result.error_code == "invalid_arguments"


def test_tool_only_reply_is_still_invalid_for_text_only(settings: Settings) -> None:
    async def run() -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json=tool_completion()))
        async with create_llm_client(settings, transport=transport) as client:
            with pytest.raises(LLMResponseError):
                await client.complete([LLMMessage(role="user", content="Hello")])

    asyncio.run(run())


@pytest.mark.parametrize(
    "failure", ["credentials", "http", "timeout", "invalid_json", "deep_json", "large"]
)
def test_tool_adapter_failures(settings: Settings, failure: str) -> None:
    expected = {
        "credentials": LLMConfigurationError,
        "http": LLMProviderError,
        "timeout": LLMTimeoutError,
        "invalid_json": LLMResponseError,
        "deep_json": LLMResponseError,
        "large": LLMResponseError,
    }[failure]

    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "credentials":
            pytest.fail("Missing credentials must not send a request")
        if failure == "timeout":
            raise httpx.ReadTimeout("fake-key", request=request)
        if failure == "http":
            return httpx.Response(401, text="fake-key")
        if failure == "deep_json":
            return httpx.Response(200, content="[" * 1500 + "]" * 1500)
        return httpx.Response(
            200, content="fake-key" if failure == "invalid_json" else "x" * 65_537
        )

    if failure == "credentials":
        settings.llm_api_key = None
    with pytest.raises(expected) as caught:
        invoke(settings, handler)
    assert "fake-key" not in str(caught.value)


def test_empty_assistant_reply_is_invalid() -> None:
    with pytest.raises(ValidationError):
        ToolAssistantMessage(role="assistant", content=None)
