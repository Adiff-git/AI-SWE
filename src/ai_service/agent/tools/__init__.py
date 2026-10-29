"""Metadata-only injection boundary for a future SWE-68 tool registry."""

from typing import Protocol


class ToolRegistry(Protocol):
    def names(self) -> tuple[str, ...]:
        """List registered capabilities without executing a tool.

        SWE-66 accepts only an empty registry. Tool definitions, argument schemas
        and execution will be agreed separately; this interface grants no access.
        """
        ...
