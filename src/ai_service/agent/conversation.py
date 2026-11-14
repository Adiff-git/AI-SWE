"""Internal, request-local conversation contracts; not public HTTP schemas."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai_service.agent.tools.schemas import ToolResult
from ai_service.integrations.llm import LLMMessage

CATALOG_NOTICE = (
    "Chưa thể truy cập catalog để kiểm tra. Đây là tư vấn chung chưa được xác minh, "
    "không phải thông tin đã xác nhận về sản phẩm, giá hoặc tồn kho."
)
VERIFIED_CATALOG_NOTICE = (
    "Đã tra cứu Backend: chỉ các trường và kết quả tra cứu được trả về là bằng chứng catalog. "
    "Nhận xét tư vấn không phải xác nhận tồn kho, bảo hành hoặc giá trong tương lai."
)
PARTIAL_CATALOG_NOTICE = (
    "Một số dữ liệu đã được tra cứu từ Backend, nhưng chưa xác minh đầy đủ các tra cứu. "
    "Chỉ sử dụng các trường trong kết quả Backend thành công; không suy đoán dữ liệu thiếu."
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
    """Request-local lookup evidence, not certification of generated prose."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: str
    session_id: str | None = None
    catalog_verified: bool = False
    catalog_evidence: tuple[ToolResult, ...] = Field(default=(), max_length=4)

    @model_validator(mode="after")
    def validate_verification(self) -> Self:
        verified = bool(self.catalog_evidence) and all(
            result.source == "backend" and result.status in ("ok", "not_found")
            for result in self.catalog_evidence
        )
        if self.catalog_verified != verified:
            raise ValueError("Verification must match all request-local lookup outcomes")
        return self
