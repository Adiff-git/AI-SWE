"""Public chat placeholder; the independent orchestrator is not wired to HTTP."""

from ai_service.agent.schemas import ChatRequest, ChatResponse


async def chat(request: ChatRequest) -> ChatResponse:
    """Return a status message; echo a supplied session ID without storing it."""
    return ChatResponse(session_id=request.session_id)
