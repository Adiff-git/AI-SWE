"""Internal, request-local conversation contracts; not public HTTP schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai_service.integrations.llm import LLMMessage

CATALOG_NOTICE = (
    "Catalog access is unavailable. This is unverified general guidance, not confirmed "
    "product, price or availability information."
)


class ConversationMessage(LLMMessage):
    """Caller-supplied history cannot introduce system instructions."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    role: Literal["user", "assistant"]


class AgentTurn(BaseModel):
    """The caller owns history and must supply it again for each turn."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    history: tuple[ConversationMessage, ...] = Field(default=(), max_length=20)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("message", "session_id")
    @classmethod
    def reject_blank_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Text must not be blank")
        return value


class AgentResult(BaseModel):
    """Advisory text only; no verified catalog facts or persisted session."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: str
    session_id: str | None = None
    catalog_verified: Literal[False] = False
