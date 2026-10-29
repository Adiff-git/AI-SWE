"""Bounded text/tool turns, with caller-owned history and no Backend operations."""

import asyncio
import json
import math
from typing import cast

from pydantic import ValidationError

from ai_service.agent.conversation import CATALOG_NOTICE, AgentResult, AgentTurn
from ai_service.agent.exceptions import (
    AgentCapabilityError,
    AgentInputError,
    AgentLimitError,
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
    ToolCallingLLMClient,
    ToolConversationMessage,
    ToolLLMResponse,
    ToolResultMessage,
)

MAX_INPUT_CHARS = 32_000
MAX_REPLY_CHARS = 8_000
MAX_TOOL_ROUNDS = 2
MAX_TOOL_CALLS = 4
MAX_CALLS_PER_REPLY = 2


class ShoppingAgent:
    """One text request, or at most two tool rounds followed by a final text turn."""

    def __init__(
        self, llm: LLMClient, *, tools: ToolRegistry | None = None, timeout: float = 30
    ) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Agent timeout must be positive and finite.")
        if tools is not None and tools.names() and not isinstance(llm, ToolCallingLLMClient):
            raise AgentCapabilityError("The injected LLM does not support tool calling.")
        self._llm = llm
        self._tools = tools
        self._timeout = timeout

    async def respond(self, turn: AgentTurn) -> AgentResult:
        with_tools = self._tools is not None and bool(self._tools.names())
        messages = build_messages(turn, with_tools=with_tools)
        if sum(len(message.content) for message in messages) > MAX_INPUT_CHARS:
            raise AgentInputError("Conversation exceeds the input character budget.")

        try:
            async with asyncio.timeout(self._timeout):
                if with_tools:
                    return await self._respond_with_tools(turn, list(messages))
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

    async def _respond_with_tools(
        self, turn: AgentTurn, messages: list[ToolConversationMessage]
    ) -> AgentResult:
        registry = cast(ToolRegistry, self._tools)
        llm = cast(ToolCallingLLMClient, self._llm)
        definitions = registry.definitions()
        seen_ids: set[str] = set()
        for round_index in range(MAX_TOOL_ROUNDS + 1):
            # Count structured IDs, arguments and schemas as well as text in tool mode.
            context = {
                "messages": [message.model_dump() for message in messages],
                "tools": [definition.model_dump() for definition in definitions],
            }
            if len(json.dumps(context, ensure_ascii=False)) > MAX_INPUT_CHARS:
                raise AgentLimitError("Tool conversation exceeds the context budget.")
            final = round_index == MAX_TOOL_ROUNDS
            reply = await llm.complete_with_tools(
                messages, definitions, tool_choice="none" if final else "auto"
            )
            if not isinstance(reply, ToolLLMResponse):
                raise AgentReplyError("The LLM returned an invalid tool reply.")
            try:
                validated = ToolLLMResponse.model_validate(reply.model_dump(warnings=False))
            except ValueError:
                raise AgentReplyError("The LLM returned an invalid tool reply.") from None
            calls = validated.message.tool_calls
            if not calls:
                if validated.finish_reason not in (None, "stop"):
                    raise AgentReplyError("The LLM did not finish a complete text answer.")
                return AgentResult(
                    answer=f"{CATALOG_NOTICE}\n\n{validated.message.content}",
                    session_id=turn.session_id,
                )
            if validated.finish_reason != "tool_calls":
                raise AgentReplyError("The LLM returned inconsistent tool calls.")
            if (
                final
                or len(calls) > MAX_CALLS_PER_REPLY
                or len(seen_ids) + len(calls) > MAX_TOOL_CALLS
            ):
                raise AgentLimitError("The LLM exceeded the tool call budget.")
            if any(call.id in seen_ids for call in calls):
                raise AgentReplyError("The LLM repeated a tool call ID.")
            seen_ids.update(call.id for call in calls)
            messages.append(validated.message)
            for call in calls:
                result = await registry.execute(call)
                messages.append(
                    ToolResultMessage(tool_call_id=call.id, content=result.model_dump_json())
                )
        raise AgentLimitError("The LLM exceeded the tool round budget.")
