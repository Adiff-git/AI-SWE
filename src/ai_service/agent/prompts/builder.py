"""Build role-separated messages without interpolating user data into policy."""

from ai_service.agent.conversation import AgentTurn
from ai_service.agent.exceptions import AgentInputError
from ai_service.agent.prompts.system import system_prompt
from ai_service.integrations.llm import LLMMessage


def build_messages(turn: AgentTurn, *, with_tools: bool = False) -> tuple[LLMMessage, ...]:
    """Copy a completed history and the current user turn after trusted policy."""
    for index, message in enumerate(turn.history):
        expected = "user" if index % 2 == 0 else "assistant"
        if message.role != expected:
            raise AgentInputError("History must contain completed user/assistant pairs.")
    if len(turn.history) % 2:
        raise AgentInputError("History must contain completed user/assistant pairs.")

    return (
        LLMMessage(role="system", content=system_prompt(with_tools=with_tools)),
        *(LLMMessage(role=message.role, content=message.content) for message in turn.history),
        LLMMessage(role="user", content=turn.message),
    )
