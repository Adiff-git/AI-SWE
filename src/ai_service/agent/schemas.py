"""Proposed chat contracts; session IDs are opaque and are not persisted."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    session_id: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
        | None
    ) = None


class ChatResponse(BaseModel):
    status: Literal["not_implemented"] = "not_implemented"
    message: str = "AI shopping assistance is not implemented yet."
    session_id: str | None = None
