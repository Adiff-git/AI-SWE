"""Text conversation contracts, independent of the provider's HTTP envelope."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LLMMessage(BaseModel):
    model_config = ConfigDict(strict=True)

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def reject_blank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message content must not be blank")
        return value


class AssistantMessage(LLMMessage):
    role: Literal["assistant"]


class LLMResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    message: AssistantMessage
    model: str = Field(min_length=1)
    finish_reason: str | None = None
