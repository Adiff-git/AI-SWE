"""Reusable LLM connection contracts and the OpenAI-compatible adapter."""

from ai_service.integrations.llm.client import (
    LLMClient,
    OpenAICompatibleLLMClient,
    ToolCallingLLMClient,
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
from ai_service.integrations.llm.schemas import (
    AssistantMessage,
    LLMMessage,
    LLMResponse,
    ToolAssistantMessage,
    ToolCall,
    ToolConversationMessage,
    ToolDefinition,
    ToolFunction,
    ToolLLMResponse,
    ToolResultMessage,
)

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
    "ToolAssistantMessage",
    "ToolCall",
    "ToolCallingLLMClient",
    "ToolConversationMessage",
    "ToolDefinition",
    "ToolFunction",
    "ToolLLMResponse",
    "ToolResultMessage",
    "create_llm_client",
]
