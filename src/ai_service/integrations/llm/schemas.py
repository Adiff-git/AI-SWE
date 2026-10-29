"""Text conversation contracts, independent of the provider's HTTP envelope."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator


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


class ToolDefinition(BaseModel):
    """Function metadata supplied by trusted application code, never by the model."""

    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    description: str = Field(min_length=1, max_length=500)
    parameters: dict[str, JsonValue]


class ToolFunction(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    arguments: str = Field(max_length=4096)

    @field_validator("arguments")
    @classmethod
    def bound_argument_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 4096:
            raise ValueError("Tool arguments exceed the byte budget")
        return value


class ToolCall(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(min_length=1, max_length=128)
    type: Literal["function"] = "function"
    function: ToolFunction

    @field_validator("id")
    @classmethod
    def reject_blank_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Tool call ID must not be blank")
        return value


class ToolAssistantMessage(BaseModel):
    model_config = ConfigDict(strict=True)

    role: Literal["assistant"]
    content: str | None = Field(default=None, max_length=8000)
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def validate_reply(self) -> ToolAssistantMessage:
        if not self.tool_calls and (self.content is None or not self.content.strip()):
            raise ValueError("An assistant reply needs text or tool calls")
        ids = [call.id for call in self.tool_calls]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate tool call IDs")
        return self


class ToolResultMessage(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    role: Literal["tool"] = "tool"
    tool_call_id: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=8192)

    @field_validator("content")
    @classmethod
    def bound_result_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 8192:
            raise ValueError("Tool result exceeds the byte budget")
        return value


type ToolConversationMessage = LLMMessage | ToolAssistantMessage | ToolResultMessage


class ToolLLMResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    message: ToolAssistantMessage
    model: str = Field(min_length=1)
    finish_reason: str | None = None
