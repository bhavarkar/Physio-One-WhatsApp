"""Exception hierarchy for LLM Gateway and Provider Adapters.

Single Organization Edition: Physio One Clinic.
Clearly distinguishes retryable from non-retryable errors for safe automated fallback.
"""
from typing import Optional, Dict, Any


class LLMError(Exception):
    """Base exception for all LLM gateway errors."""
    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        is_retryable: bool = False,
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.is_retryable = is_retryable
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "provider": self.provider,
            "is_retryable": self.is_retryable,
            "status_code": self.status_code,
            "details": self.details,
        }


class LLMConfigurationError(LLMError):
    """Raised when provider configuration, credentials, or URLs are invalid."""
    def __init__(self, message: str, provider: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, provider=provider, is_retryable=False, status_code=400, details=details)


class LLMAuthenticationError(LLMError):
    """Raised when provider rejects credentials (HTTP 401/403). Non-retryable."""
    def __init__(self, message: str, provider: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, provider=provider, is_retryable=False, status_code=401, details=details)


class LLMRateLimitError(LLMError):
    """Raised when rate limit or quota is exceeded (HTTP 429). Retryable with backoff or fallback."""
    def __init__(self, message: str, provider: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, provider=provider, is_retryable=True, status_code=429, details=details)


class LLMTimeoutError(LLMError):
    """Raised when upstream provider times out. Retryable."""
    def __init__(self, message: str, provider: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, provider=provider, is_retryable=True, status_code=504, details=details)


class LLMServiceUnavailableError(LLMError):
    """Raised when upstream provider returns 5xx outage or connection failure. Retryable."""
    def __init__(self, message: str, provider: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, provider=provider, is_retryable=True, status_code=503, details=details)


class LLMContextLengthExceededError(LLMError):
    """Raised when prompt exceeds model context window limit. Non-retryable."""
    def __init__(self, message: str, provider: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, provider=provider, is_retryable=False, status_code=400, details=details)


class LLMUnsupportedCapabilityError(LLMError):
    """Raised when a requested feature (e.g. tools, streaming) is not supported by the provider."""
    def __init__(self, message: str, provider: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, provider=provider, is_retryable=False, status_code=400, details=details)


class LLMResponseParsingError(LLMError):
    """Raised when provider returns an unparseable response payload."""
    def __init__(self, message: str, provider: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, provider=provider, is_retryable=False, status_code=502, details=details)
