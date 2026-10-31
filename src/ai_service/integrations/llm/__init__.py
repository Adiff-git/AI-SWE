"""Reusable LLM connection contracts and the OpenAI-compatible adapter."""

from ai_service.integrations.llm.client import (
    LLMClient,
    OpenAICompatibleLLMClient,
    create_llm_client,
)
from ai_service.integrations.llm.exceptions import (
    LLMConfigurationError,
    LLMConnectionError,
    LLMError,
    LLMProviderError,
    LLMResponseError,
    LLMTimeoutError,
)
from ai_service.integrations.llm.schemas import AssistantMessage, LLMMessage, LLMResponse

__all__ = [
    "AssistantMessage",
    "LLMClient",
    "LLMConfigurationError",
    "LLMConnectionError",
    "LLMError",
    "LLMMessage",
    "LLMProviderError",
    "LLMResponse",
    "LLMResponseError",
    "LLMTimeoutError",
    "OpenAICompatibleLLMClient",
    "create_llm_client",
]
