import asyncio
import json
from collections.abc import Callable

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import AnyHttpUrl, SecretStr, ValidationError

from ai_service import main
from ai_service.core.config import Settings
from ai_service.integrations.llm import (
    LLMConfigurationError,
    LLMConnectionError,
    LLMMessage,
    LLMProviderError,
    LLMResponse,
    LLMResponseError,
    LLMTimeoutError,
    create_llm_client,
)

KEY = "unit-test-secret"
MESSAGES = [LLMMessage(role="user", content="Hello")]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        llm_api_key=KEY,
        llm_base_url="https://provider.example/v1",
        llm_model="test-model",
        llm_timeout=7,
    )


def completion(**message_fields: object) -> dict[str, object]:
    return {
        "model": "test-model",
        "choices": [
            {
                "message": {"role": "assistant", "content": "Hello back!", **message_fields},
                "finish_reason": "stop",
            }
        ],
        "usage": {"total_tokens": 10},
    }


def invoke(settings: Settings, handler: Callable[[httpx.Request], httpx.Response]) -> LLMResponse:
    async def run() -> LLMResponse:
        async with create_llm_client(settings, transport=httpx.MockTransport(handler)) as client:
            return await client.complete(MESSAGES)

    return asyncio.run(run())


@pytest.mark.parametrize("suffix", ["", "/"])
def test_success(settings: Settings, suffix: str) -> None:
    settings.llm_base_url = AnyHttpUrl(f"https://provider.example/v1{suffix}")
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert str(request.url) == "https://provider.example/v1/chat/completions"
        assert request.headers["Authorization"] == f"Bearer {KEY}"
        assert request.headers["Content-Type"] == "application/json"
        assert request.extensions["timeout"] == dict.fromkeys(
            ["connect", "read", "write", "pool"], 7
        )
        assert json.loads(request.content) == {
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": False,
        }
        return httpx.Response(200, json=completion())

    result = invoke(settings, handler)
    assert len(requests) == 1
    assert result.message.role == "assistant"
    assert result.message.content == "Hello back!"
    assert result.model == "test-model"
    assert result.finish_reason == "stop"


@pytest.mark.parametrize("field", ["llm_api_key", "llm_base_url", "llm_model"])
def test_missing_configuration(settings: Settings, field: str) -> None:
    setattr(settings, field, None)

    def handler(request: httpx.Request) -> httpx.Response:
        pytest.fail("Missing configuration must not send a request")

    with pytest.raises(LLMConfigurationError, match=field.upper()):
        invoke(settings, handler)


def test_blank_secret(settings: Settings) -> None:
    settings.llm_api_key = SecretStr(" ")
    with pytest.raises(LLMConfigurationError, match="LLM_API_KEY"):
        invoke(settings, lambda request: pytest.fail("Must not send a request"))


@pytest.mark.parametrize("status", [302, 400, 401, 429, 500, 503])
def test_provider_error(settings: Settings, status: int, caplog: pytest.LogCaptureFixture) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            status,
            json={"error": f"Sensitive provider detail {KEY}"},
            headers={"Location": "https://other.example/v1/chat/completions"},
        )

    with pytest.raises(LLMProviderError) as error:
        invoke(settings, handler)
    assert error.value.status_code == status
    assert str(error.value) == f"LLM provider returned HTTP {status}."
    assert KEY not in caplog.text
    assert len(requests) == 1


@pytest.mark.parametrize(
    ("http_error", "expected"),
    [
        (httpx.ConnectTimeout, LLMTimeoutError),
        (httpx.ReadTimeout, LLMTimeoutError),
        (httpx.ConnectError, LLMConnectionError),
        (httpx.ReadError, LLMConnectionError),
    ],
)
def test_network_errors(
    settings: Settings,
    http_error: type[httpx.RequestError],
    expected: type[Exception],
    caplog: pytest.LogCaptureFixture,
) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise http_error(f"Sensitive transport detail {KEY}", request=request)

    with pytest.raises(expected) as error:
        invoke(settings, handler)
    assert KEY not in str(error.value)
    assert KEY not in caplog.text
    assert len(requests) == 1


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"model": "test-model", "choices": []},
        {"model": "test-model", "choices": [{}]},
        {"choices": [{"message": {"role": "assistant", "content": "Hello"}}]},
        {"model": "test-model", "choices": [{"message": {"content": "Hello"}}]},
        {"model": "test-model", "choices": [{"message": {"role": "assistant"}}]},
        completion(role="user"),
        completion(content=None),
        completion(content=123),
        completion(content=[]),
        completion(content=""),
        completion(content="   "),
    ],
)
def test_invalid_response(settings: Settings, payload: object) -> None:
    with pytest.raises(LLMResponseError):
        invoke(settings, lambda request: httpx.Response(200, json=payload))


def test_invalid_json(settings: Settings) -> None:
    with pytest.raises(LLMResponseError) as error:
        invoke(settings, lambda request: httpx.Response(200, content=f"not JSON {KEY}"))
    assert KEY not in str(error.value)


def test_conversation_reuses_client(settings: Settings) -> None:
    messages = [
        LLMMessage(role="system", content="Preserve the conversation."),
        *MESSAGES,
        LLMMessage(role="assistant", content="Hello back!"),
        LLMMessage(role="user", content="Another message"),
    ]
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert json.loads(request.content)["messages"] == [m.model_dump() for m in messages]
        return httpx.Response(200, json=completion(content="  Keep whitespace.\n"))

    async def run() -> None:
        async with create_llm_client(settings, transport=httpx.MockTransport(handler)) as client:
            for _ in range(2):
                response = await client.complete(messages)
                assert response.message.content == "  Keep whitespace.\n"

    asyncio.run(run())
    assert len(requests) == 2


def test_empty_conversation(settings: Settings) -> None:
    async def run() -> None:
        transport = httpx.MockTransport(lambda request: pytest.fail("Must not send a request"))
        async with create_llm_client(settings, transport=transport) as client:
            with pytest.raises(ValueError, match="At least one"):
                await client.complete([])

    asyncio.run(run())


@pytest.mark.parametrize("content", ["", "  ", None, 123])
def test_invalid_input_message(content: object) -> None:
    with pytest.raises(ValidationError):
        LLMMessage(role="user", content=content)


class TrackingTransport(httpx.MockTransport):
    closed = False

    async def aclose(self) -> None:
        self.closed = True
        await super().aclose()


def test_pool_closes_on_failure(settings: Settings) -> None:
    transport = TrackingTransport(lambda request: httpx.Response(500))

    async def run() -> None:
        with pytest.raises(LLMProviderError):
            async with create_llm_client(settings, transport=transport) as client:
                await client.complete(MESSAGES)

    asyncio.run(run())
    assert transport.closed


def test_app_lifecycle_without_llm_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        _env_file=None, llm_api_key=None, llm_base_url=None, llm_model=None, llm_timeout=30
    )
    transport = TrackingTransport(lambda request: pytest.fail("Startup must not call LLM"))
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(
        main, "create_llm_client", lambda settings: create_llm_client(settings, transport=transport)
    )

    async def reject_request(*args: object, **kwargs: object) -> httpx.Response:
        pytest.fail("Placeholder endpoints must not make outbound requests")

    monkeypatch.setattr(httpx.AsyncClient, "request", reject_request)
    with TestClient(main.app) as client:
        assert not transport.closed
        assert main.app.state.llm_client is not None
        assert client.get("/api/v1/health").json() == {"status": "ok"}
        assert client.post("/api/v1/chat", json={"message": "Hello"}).json() == {
            "status": "not_implemented",
            "message": "AI shopping assistance is not implemented yet.",
            "session_id": None,
        }
    assert transport.closed
