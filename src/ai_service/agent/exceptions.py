"""Controlled orchestration failures without raw messages or provider details."""


class AgentError(Exception):
    """Base failure for an agent turn."""


class AgentInputError(AgentError):
    """The conversation order or request budget is invalid."""


class AgentLLMError(AgentError):
    """The injected LLM dependency failed."""


class AgentReplyError(AgentError):
    """The LLM did not return a valid, complete text answer."""


class AgentCapabilityError(AgentError):
    """A turn requires an unsupported capability."""


class AgentTimeoutError(AgentError):
    """The orchestration deadline expired."""


class AgentLimitError(AgentError):
    """Tool processing exceeded a round, call or context budget."""
