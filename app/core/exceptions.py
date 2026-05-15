"""
Production-grade exception hierarchy for error handling.
All exceptions include proper context and error codes.
"""
from enum import Enum
from typing import Any, Optional


class ErrorCode(str, Enum):
    """Standard error codes for API responses."""

    # Auth errors
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"

    # Validation errors
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_REQUEST = "INVALID_REQUEST"

    # Resource errors
    NOT_FOUND = "NOT_FOUND"
    DUPLICATE = "DUPLICATE"
    CONFLICT = "CONFLICT"

    # Integration errors
    CONNECTOR_ERROR = "CONNECTOR_ERROR"
    SYNC_ERROR = "SYNC_ERROR"
    OAUTH_ERROR = "OAUTH_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"

    # AI errors
    LLM_ERROR = "LLM_ERROR"
    EXTRACTION_ERROR = "EXTRACTION_ERROR"

    # Scheduling errors
    SCHEDULING_ERROR = "SCHEDULING_ERROR"

    # Internal errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"


class WorkloadError(Exception):
    """Base exception for all workload errors."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        status_code: int = 500,
        details: Optional[dict[str, Any]] = None,
    ):
        """Initialize error with context."""
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary for API response."""
        return {
            "error": self.error_code.value,
            "message": self.message,
            "details": self.details,
        }


class AuthenticationError(WorkloadError):
    """Authentication failed."""

    def __init__(self, message: str = "Authentication failed", details: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.INVALID_CREDENTIALS,
            status_code=401,
            details=details,
        )


class AuthorizationError(WorkloadError):
    """User not authorized for resource."""

    def __init__(self, message: str = "Not authorized", details: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.FORBIDDEN,
            status_code=403,
            details=details,
        )


class ValidationError(WorkloadError):
    """Input validation failed."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=422,
            details=details,
        )


class NotFoundError(WorkloadError):
    """Resource not found."""

    def __init__(self, message: str = "Resource not found", details: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.NOT_FOUND,
            status_code=404,
            details=details,
        )


class DuplicateError(WorkloadError):
    """Resource already exists."""

    def __init__(self, message: str = "Resource already exists", details: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.DUPLICATE,
            status_code=409,
            details=details,
        )


class ConnectorError(WorkloadError):
    """Error in external connector."""

    def __init__(self, message: str, connector: str = "", details: Optional[dict] = None):
        if not details:
            details = {}
        details["connector"] = connector
        super().__init__(
            message=message,
            error_code=ErrorCode.CONNECTOR_ERROR,
            status_code=502,
            details=details,
        )


class OAuthError(WorkloadError):
    """OAuth authentication flow failed."""

    def __init__(self, message: str, provider: str = "", details: Optional[dict] = None):
        if not details:
            details = {}
        details["provider"] = provider
        super().__init__(
            message=message,
            error_code=ErrorCode.OAUTH_ERROR,
            status_code=401,
            details=details,
        )


class RateLimitError(WorkloadError):
    """Rate limit exceeded."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = 60, details: Optional[dict] = None):
        if not details:
            details = {}
        details["retry_after"] = retry_after
        super().__init__(
            message=message,
            error_code=ErrorCode.RATE_LIMIT_ERROR,
            status_code=429,
            details=details,
        )


class SyncError(WorkloadError):
    """Error during sync operation."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.SYNC_ERROR,
            status_code=502,
            details=details,
        )


class LLMError(WorkloadError):
    """Error in LLM call."""

    def __init__(self, message: str, provider: str = "", details: Optional[dict] = None):
        if not details:
            details = {}
        details["provider"] = provider
        super().__init__(
            message=message,
            error_code=ErrorCode.LLM_ERROR,
            status_code=502,
            details=details,
        )


class ExtractionError(WorkloadError):
    """Error in AI extraction pipeline."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.EXTRACTION_ERROR,
            status_code=502,
            details=details,
        )


class SchedulingError(WorkloadError):
    """Error in scheduling engine."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.SCHEDULING_ERROR,
            status_code=502,
            details=details,
        )


class DatabaseError(WorkloadError):
    """Database operation failed."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.DATABASE_ERROR,
            status_code=503,
            details=details,
        )


class TimeoutError(WorkloadError):
    """Operation timeout."""

    def __init__(self, message: str = "Operation timeout", details: Optional[dict] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.TIMEOUT_ERROR,
            status_code=504,
            details=details,
        )
