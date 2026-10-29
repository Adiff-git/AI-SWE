"""Versioned system policy and role-safe conversation assembly."""

from ai_service.agent.prompts.builder import build_messages
from ai_service.agent.prompts.system import SYSTEM_PROMPT, SYSTEM_PROMPT_VERSION, system_prompt

__all__ = ["SYSTEM_PROMPT", "SYSTEM_PROMPT_VERSION", "build_messages", "system_prompt"]
