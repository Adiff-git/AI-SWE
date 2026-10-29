"""One bounded LLM turn, with caller-owned history and no Backend operations."""

import asyncio
import math

from pydantic import ValidationError

from ai_service.agent.conversation import CATALOG_NOTICE, AgentResult, AgentTurn
from ai_service.agent.exceptions import (
    AgentCapabilityError,
    AgentInputError,
    AgentLLMError,
    AgentReplyError,
    AgentTimeoutError,
)
from ai_service.agent.prompts import build_messages
from ai_service.agent.tools import ToolRegistry
from ai_service.integrations.llm import (
    AssistantMessage,
    LLMClient,
    LLMError,
    LLMResponse,
)

MAX_INPUT_CHARS = 32_000
MAX_REPLY_CHARS = 8_000


class ShoppingAgent:
    """Inject an LLM; each call owns its messages and makes at most one request."""

    def __init__(
        self, llm: LLMClient, *, tools: ToolRegistry | None = None, timeout: float = 30
    ) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Agent timeout must be positive and finite.")
        if tools is not None and tools.names():
            raise AgentCapabilityError("Tool execution is not supported by this agent yet.")
        self._llm = llm
        self._timeout = timeout

    async def respond(self, turn: AgentTurn) -> AgentResult:
        messages = build_messages(turn)
        if sum(len(message.content) for message in messages) > MAX_INPUT_CHARS:
            raise AgentInputError("Conversation exceeds the input character budget.")

        try:
            async with asyncio.timeout(self._timeout):
                reply = await self._llm.complete(messages)
        except TimeoutError:
            raise AgentTimeoutError("Agent turn exceeded its deadline.") from None
        except LLMError:
            raise AgentLLMError("The LLM could not complete this agent turn.") from None

        # Validate even injected implementations that bypass SWE-65's HTTP adapter.
        reply_message = getattr(reply, "message", None)
        if not isinstance(reply, LLMResponse) or not isinstance(reply_message, AssistantMessage):
            raise AgentReplyError("The LLM returned an invalid assistant reply.")
        try:
            validated = LLMResponse.model_validate(
                {
                    "message": {
                        "role": getattr(reply_message, "role", None),
                        "content": getattr(reply_message, "content", None),
                    },
                    "model": getattr(reply, "model", None),
                    "finish_reason": getattr(reply, "finish_reason", None),
                }
            )
        except ValidationError:
            raise AgentReplyError("The LLM returned an invalid assistant reply.") from None

        if validated.finish_reason in ("tool_calls", "function_call"):
            raise AgentCapabilityError("The LLM requested unsupported tool execution.")
        if validated.finish_reason not in (None, "stop"):
            raise AgentReplyError("The LLM did not finish a complete text answer.")
        if len(validated.message.content) > MAX_REPLY_CHARS:
            raise AgentReplyError("The LLM reply exceeds the output character budget.")

        return AgentResult(
            answer=f"{CATALOG_NOTICE}\n\n{validated.message.content}",
            session_id=turn.session_id,
        )
