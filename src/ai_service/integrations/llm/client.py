"""Async Chat Completions adapter and its explicitly owned HTTP connection pool."""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field

from ai_service.core.config import Settings
from ai_service.integrations.llm.exceptions import (
    LLMConfigurationError,
    LLMConnectionError,
    LLMProviderError,
    LLMResponseError,
    LLMTimeoutError,
)
from ai_service.integrations.llm.schemas import AssistantMessage, LLMMessage, LLMResponse


class LLMClient(Protocol):
    async def complete(self, messages: Sequence[LLMMessage]) -> LLMResponse:
        """Return a validated assistant response for a text conversation."""
        ...


class _Choice(BaseModel):
    model_config = ConfigDict(strict=True)

    message: AssistantMessage
    finish_reason: str | None = None


class _Completion(BaseModel):
    model_config = ConfigDict(strict=True)

    model: str = Field(min_length=1)
    choices: list[_Choice] = Field(min_length=1)


class OpenAICompatibleLLMClient:
    """Use a caller-owned HTTP client; construction performs no network I/O."""

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http_client = http_client

    async def complete(self, messages: Sequence[LLMMessage]) -> LLMResponse:
        settings = self._settings
        key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else ""
        missing = []
        if not key.strip():
            missing.append("LLM_API_KEY")
        if settings.llm_base_url is None:
            missing.append("LLM_BASE_URL")
        if not settings.llm_model:
            missing.append("LLM_MODEL")
        if missing:
            raise LLMConfigurationError(f"Missing LLM configuration: {', '.join(missing)}.")
        if not messages:
            raise ValueError("At least one conversation message is required.")

        url = f"{str(settings.llm_base_url).rstrip('/')}/chat/completions"
        try:
            response = await self._http_client.post(
                url,
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": settings.llm_model,
                    "messages": [message.model_dump() for message in messages],
                    "stream": False,
                },
                timeout=settings.llm_timeout,
                follow_redirects=False,
            )
            response.raise_for_status()
        except httpx.TimeoutException:
            raise LLMTimeoutError("LLM request timed out.") from None
        except httpx.HTTPStatusError as exc:
            raise LLMProviderError(exc.response.status_code) from None
        except httpx.RequestError:
            raise LLMConnectionError("LLM request failed due to a network error.") from None

        try:
            completion = _Completion.model_validate(response.json())
        except ValueError:
            raise LLMResponseError("LLM provider returned an invalid chat completion.") from None

        choice = completion.choices[0]
        return LLMResponse(
            message=choice.message,
            model=completion.model,
            finish_reason=choice.finish_reason,
        )


@asynccontextmanager
async def create_llm_client(
    settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
) -> AsyncIterator[LLMClient]:
    """Own a reusable pool, closing it on exit even when an invocation fails."""
    async with httpx.AsyncClient(
        timeout=settings.llm_timeout, follow_redirects=False, transport=transport
    ) as http_client:
        yield OpenAICompatibleLLMClient(settings, http_client)
