"""Provider-independent failures with credential-free error messages."""


class LLMError(Exception):
    """Base error for LLM invocation failures."""


class LLMConfigurationError(LLMError):
    """Required LLM configuration is missing."""


class LLMProviderError(LLMError):
    """The provider returned an unsuccessful HTTP status."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"LLM provider returned HTTP {status_code}.")


class LLMTimeoutError(LLMError):
    """An LLM request timed out."""


class LLMConnectionError(LLMError):
    """An LLM request failed at the transport layer."""


class LLMResponseError(LLMError):
    """The provider response could not be validated."""
