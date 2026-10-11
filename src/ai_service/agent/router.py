from fastapi import APIRouter

from ai_service.agent.schemas import ChatRequest, ChatResponse
from ai_service.agent.service import chat

router = APIRouter(tags=["agent"])


@router.post("/chat", response_model=ChatResponse)
async def chat_message(request: ChatRequest) -> ChatResponse:
    """Report that AI shopping assistance is not implemented yet."""
    return await chat(request)
