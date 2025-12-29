"""
Custom Exceptions for LUKi API Gateway

Provides a structured exception hierarchy with automatic HTTP response generation
for consistent error handling across the gateway.
"""

from typing import Optional, Dict, Any
from .constants import HttpStatus, ErrorCodes, ErrorMessages


class GatewayError(Exception):
    """
    Base exception for all API Gateway errors.
    
    Automatically generates structured error responses suitable for HTTP APIs.
    
    Attributes:
        message: Human-readable error message
        error_code: Machine-readable error code
        status_code: HTTP status code
        details: Additional context about the error
    """
    
    def __init__(
        self,
        message: str,
        error_code: str = ErrorCodes.UNKNOWN_ERROR,
        status_code: int = HttpStatus.INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for API responses"""
        response = {
            "error": self.error_code,
            "message": self.message,
        }
        if self.details:
            response["details"] = self.details
        return response
    
    def to_response(self) -> Dict[str, Any]:
        """Generate full HTTP response structure"""
        return {
            "status_code": self.status_code,
            "content": self.to_dict()
        }


# =============================================================================
# AUTHENTICATION ERRORS
# =============================================================================

class AuthenticationError(GatewayError):
    """Raised when authentication fails"""
    
    def __init__(
        self,
        message: str = ErrorMessages.UNAUTHORIZED,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code=ErrorCodes.UNAUTHORIZED,
            status_code=HttpStatus.UNAUTHORIZED,
            details=details
        )


class InvalidTokenError(AuthenticationError):
    """Raised when JWT or API token is invalid"""
    
    def __init__(self, message: str = "Invalid authentication token"):
        super().__init__(message=message)
        self.error_code = ErrorCodes.INVALID_TOKEN


class TokenExpiredError(AuthenticationError):
    """Raised when authentication token has expired"""
    
    def __init__(self, message: str = "Authentication token has expired"):
        super().__init__(message=message)
        self.error_code = ErrorCodes.TOKEN_EXPIRED


class InvalidApiKeyError(AuthenticationError):
    """Raised when API key is invalid"""
    
    def __init__(self, message: str = "Invalid API key"):
        super().__init__(message=message)
        self.error_code = ErrorCodes.INVALID_API_KEY


# =============================================================================
# AUTHORIZATION ERRORS
# =============================================================================

class AuthorizationError(GatewayError):
    """Raised when authorization fails"""
    
    def __init__(
        self,
        message: str = ErrorMessages.FORBIDDEN,
        required_permission: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        details = details or {}
        if required_permission:
            details["required_permission"] = required_permission
        super().__init__(
            message=message,
            error_code=ErrorCodes.FORBIDDEN,
            status_code=HttpStatus.FORBIDDEN,
            details=details
        )


# =============================================================================
# VALIDATION ERRORS
# =============================================================================

class ValidationError(GatewayError):
    """Raised when request validation fails"""
    
    def __init__(
        self,
        message: str = ErrorMessages.VALIDATION_FAILED,
        field: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        details = details or {}
        if field:
            details["field"] = field
        super().__init__(
            message=message,
            error_code=ErrorCodes.VALIDATION_ERROR,
            status_code=HttpStatus.UNPROCESSABLE_ENTITY,
            details=details
        )


class MissingFieldError(ValidationError):
    """Raised when a required field is missing"""
    
    def __init__(self, field: str):
        super().__init__(
            message=f"Required field '{field}' is missing",
            field=field
        )
        self.error_code = ErrorCodes.MISSING_FIELD


class InvalidFormatError(ValidationError):
    """Raised when field format is invalid"""
    
    def __init__(self, field: str, expected_format: str):
        super().__init__(
            message=f"Field '{field}' has invalid format, expected: {expected_format}",
            field=field,
            details={"expected_format": expected_format}
        )
        self.error_code = ErrorCodes.INVALID_FORMAT


# =============================================================================
# RATE LIMITING ERRORS
# =============================================================================

class RateLimitError(GatewayError):
    """Raised when rate limit is exceeded"""
    
    def __init__(
        self,
        message: str = ErrorMessages.RATE_LIMITED,
        retry_after: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        details = details or {}
        if retry_after:
            details["retry_after_seconds"] = retry_after
        super().__init__(
            message=message,
            error_code=ErrorCodes.RATE_LIMITED,
            status_code=HttpStatus.TOO_MANY_REQUESTS,
            details=details
        )


# =============================================================================
# RESOURCE ERRORS
# =============================================================================

class NotFoundError(GatewayError):
    """Raised when requested resource is not found"""
    
    def __init__(
        self,
        resource_type: str = "Resource",
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        message = f"{resource_type} not found"
        if resource_id:
            message = f"{resource_type} '{resource_id}' not found"
        details = details or {}
        if resource_id:
            details["resource_id"] = resource_id
        super().__init__(
            message=message,
            error_code=ErrorCodes.NOT_FOUND,
            status_code=HttpStatus.NOT_FOUND,
            details=details
        )


class ConflictError(GatewayError):
    """Raised when there's a resource conflict"""
    
    def __init__(
        self,
        message: str = "Resource conflict",
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            error_code=ErrorCodes.CONFLICT,
            status_code=HttpStatus.CONFLICT,
            details=details
        )


# =============================================================================
# UPSTREAM SERVICE ERRORS
# =============================================================================

class UpstreamError(GatewayError):
    """Raised when an upstream service fails"""
    
    def __init__(
        self,
        service_name: str,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        details = details or {}
        details["service"] = service_name
        super().__init__(
            message=message or f"Upstream service '{service_name}' error",
            error_code=ErrorCodes.UPSTREAM_ERROR,
            status_code=HttpStatus.BAD_GATEWAY,
            details=details
        )


class ServiceUnavailableError(GatewayError):
    """Raised when a service is unavailable"""
    
    def __init__(
        self,
        service_name: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        message = ErrorMessages.SERVICE_UNAVAILABLE
        details = details or {}
        if service_name:
            message = f"Service '{service_name}' is temporarily unavailable"
            details["service"] = service_name
        super().__init__(
            message=message,
            error_code=ErrorCodes.SERVICE_UNAVAILABLE,
            status_code=HttpStatus.SERVICE_UNAVAILABLE,
            details=details
        )


class TimeoutError(GatewayError):
    """Raised when a request times out"""
    
    def __init__(
        self,
        service_name: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        message = "Request timed out"
        details = details or {}
        if service_name:
            message = f"Request to '{service_name}' timed out"
            details["service"] = service_name
        if timeout_seconds:
            details["timeout_seconds"] = timeout_seconds
        super().__init__(
            message=message,
            error_code=ErrorCodes.TIMEOUT,
            status_code=HttpStatus.GATEWAY_TIMEOUT,
            details=details
        )
