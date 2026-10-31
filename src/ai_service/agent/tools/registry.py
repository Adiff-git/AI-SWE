"""Allowlisted typed dispatch with bounded, credential-free results."""

import asyncio
import json
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from ai_service.agent.tools.provider import ProductProviderUnavailable
from ai_service.agent.tools.schemas import ToolData, ToolResult, ToolSource
from ai_service.integrations.llm import ToolCall, ToolDefinition


class _InvalidArguments(Exception):
    pass


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON constant")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


@dataclass(frozen=True)
class Tool[Arguments: BaseModel]:
    name: str
    description: str
    arguments: type[Arguments]
    handler: Callable[[Arguments], Awaitable[ToolData | None]]
    source: ToolSource
    read_only: bool = True

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.arguments.model_json_schema(),
        )

    async def invoke(self, raw: str) -> ToolData | None:
        try:
            value = json.loads(
                raw, parse_constant=_reject_constant, object_pairs_hook=_unique_object
            )
            if not isinstance(value, dict):
                raise ValueError("Arguments must be an object")
            arguments = self.arguments.model_validate(value)
        except (ValueError, RecursionError):
            raise _InvalidArguments from None
        return await self.handler(arguments)


class ToolRegistry:
    def __init__(self, *, timeout: float = 5) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Tool timeout must be positive and finite.")
        self._timeout = timeout
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        definition = tool.definition()
        if definition.name in self._tools:
            raise ValueError("Duplicate tool name.")
        if tool.read_only is not True or tool.source not in ("fake", "unavailable"):
            raise ValueError("Only read-only fake/unavailable product tools are supported.")
        if len(json.dumps(definition.model_dump(), ensure_ascii=False).encode("utf-8")) > 8192:
            raise ValueError("Tool definition exceeds the byte budget.")
        self._tools[definition.name] = tool

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(tool.definition() for tool in self._tools.values())

    async def execute(self, call: ToolCall) -> ToolResult:
        tool = self._tools.get(call.function.name)
        base = {
            "tool_call_id": call.id,
            "name": call.function.name,
            "source": tool.source if tool else "unavailable",
        }
        if tool is None:
            return ToolResult(**base, status="error", error_code="unknown_tool")
        try:
            async with asyncio.timeout(self._timeout):
                data = await tool.invoke(call.function.arguments)
            # Revalidate provider/handler models, including instances built without validation.
            payload = data.model_dump(warnings=False) if isinstance(data, BaseModel) else data
            result = ToolResult.model_validate(
                {**base, "status": "not_found" if data is None else "ok", "data": payload}
            )
        except _InvalidArguments:
            return ToolResult(**base, status="error", error_code="invalid_arguments")
        except ProductProviderUnavailable:
            return ToolResult(**base, status="not_available")
        except TimeoutError:
            return ToolResult(**base, status="error", error_code="timeout")
        except ValidationError:
            return ToolResult(**base, status="error", error_code="invalid_result")
        except Exception:
            return ToolResult(**base, status="error", error_code="tool_error")
        if len(result.model_dump_json().encode("utf-8")) > 8192:
            return ToolResult(**base, status="error", error_code="result_too_large")
        return result
