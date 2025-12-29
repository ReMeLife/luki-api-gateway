"""
Constants for LUKi API Gateway

Centralized HTTP status codes, error messages, header names, and configuration constants.
Provides a single source of truth for gateway-level configuration.
"""

from typing import Final

# =============================================================================
# SERVICE IDENTIFICATION
# =============================================================================

SERVICE_NAME: Final[str] = "luki-api-gateway"
SERVICE_VERSION: Final[str] = "1.0.0"

# =============================================================================
# HTTP STATUS CODES
# =============================================================================

class HttpStatus:
    """Standard HTTP status codes"""
    OK: Final[int] = 200
    CREATED: Final[int] = 201
    ACCEPTED: Final[int] = 202
    NO_CONTENT: Final[int] = 204
    BAD_REQUEST: Final[int] = 400
    UNAUTHORIZED: Final[int] = 401
    FORBIDDEN: Final[int] = 403
    NOT_FOUND: Final[int] = 404
    METHOD_NOT_ALLOWED: Final[int] = 405
    CONFLICT: Final[int] = 409
    UNPROCESSABLE_ENTITY: Final[int] = 422
    TOO_MANY_REQUESTS: Final[int] = 429
    INTERNAL_SERVER_ERROR: Final[int] = 500
    BAD_GATEWAY: Final[int] = 502
    SERVICE_UNAVAILABLE: Final[int] = 503
    GATEWAY_TIMEOUT: Final[int] = 504


# =============================================================================
# HTTP HEADERS
# =============================================================================

class Headers:
    """Standard and custom HTTP header names"""
    # Standard headers
    CONTENT_TYPE: Final[str] = "Content-Type"
    AUTHORIZATION: Final[str] = "Authorization"
    ACCEPT: Final[str] = "Accept"
    CACHE_CONTROL: Final[str] = "Cache-Control"
    
    # Custom LUKi headers
    CORRELATION_ID: Final[str] = "X-Correlation-ID"
    REQUEST_ID: Final[str] = "X-Request-ID"
    USER_ID: Final[str] = "X-User-ID"
    API_KEY: Final[str] = "X-API-Key"
    RATE_LIMIT_REMAINING: Final[str] = "X-RateLimit-Remaining"
    RATE_LIMIT_RESET: Final[str] = "X-RateLimit-Reset"
    RESPONSE_TIME: Final[str] = "X-Response-Time"


# =============================================================================
# CONTENT TYPES
# =============================================================================

class ContentTypes:
    """Common content type values"""
    JSON: Final[str] = "application/json"
    TEXT: Final[str] = "text/plain"
    HTML: Final[str] = "text/html"
    FORM: Final[str] = "application/x-www-form-urlencoded"
    MULTIPART: Final[str] = "multipart/form-data"
    EVENT_STREAM: Final[str] = "text/event-stream"


# =============================================================================
# ERROR CODES
# =============================================================================

class ErrorCodes:
    """Standardized error codes for API responses"""
    # General errors
    UNKNOWN_ERROR: Final[str] = "UNKNOWN_ERROR"
    INTERNAL_ERROR: Final[str] = "INTERNAL_ERROR"
    
    # Validation errors
    VALIDATION_ERROR: Final[str] = "VALIDATION_ERROR"
    INVALID_REQUEST: Final[str] = "INVALID_REQUEST"
    MISSING_FIELD: Final[str] = "MISSING_FIELD"
    INVALID_FORMAT: Final[str] = "INVALID_FORMAT"
    
    # Authentication/Authorization errors
    UNAUTHORIZED: Final[str] = "UNAUTHORIZED"
    FORBIDDEN: Final[str] = "FORBIDDEN"
    INVALID_TOKEN: Final[str] = "INVALID_TOKEN"
    TOKEN_EXPIRED: Final[str] = "TOKEN_EXPIRED"
    INVALID_API_KEY: Final[str] = "INVALID_API_KEY"
    
    # Rate limiting
    RATE_LIMITED: Final[str] = "RATE_LIMITED"
    QUOTA_EXCEEDED: Final[str] = "QUOTA_EXCEEDED"
    
    # Service errors
    SERVICE_UNAVAILABLE: Final[str] = "SERVICE_UNAVAILABLE"
    UPSTREAM_ERROR: Final[str] = "UPSTREAM_ERROR"
    TIMEOUT: Final[str] = "TIMEOUT"
    
    # Resource errors
    NOT_FOUND: Final[str] = "NOT_FOUND"
    CONFLICT: Final[str] = "CONFLICT"
    ALREADY_EXISTS: Final[str] = "ALREADY_EXISTS"


# =============================================================================
# ERROR MESSAGES
# =============================================================================

class ErrorMessages:
    """Standard error messages for API responses"""
    UNAUTHORIZED: Final[str] = "Authentication required"
    FORBIDDEN: Final[str] = "Access denied"
    NOT_FOUND: Final[str] = "Resource not found"
    RATE_LIMITED: Final[str] = "Too many requests, please try again later"
    INTERNAL_ERROR: Final[str] = "An internal error occurred"
    SERVICE_UNAVAILABLE: Final[str] = "Service temporarily unavailable"
    INVALID_REQUEST: Final[str] = "Invalid request format"
    VALIDATION_FAILED: Final[str] = "Request validation failed"


# =============================================================================
# RATE LIMITING
# =============================================================================

class RateLimits:
    """Rate limiting configuration constants"""
    DEFAULT_REQUESTS_PER_MINUTE: Final[int] = 60
    DEFAULT_REQUESTS_PER_HOUR: Final[int] = 1000
    CHAT_REQUESTS_PER_MINUTE: Final[int] = 20
    UPLOAD_REQUESTS_PER_MINUTE: Final[int] = 10
    IMAGE_GENERATION_PER_DAY: Final[int] = 50


# =============================================================================
# TIMEOUT CONFIGURATION (seconds)
# =============================================================================

class Timeouts:
    """Timeout values for various operations"""
    DEFAULT_REQUEST: Final[int] = 30
    CHAT_REQUEST: Final[int] = 120
    STREAMING_REQUEST: Final[int] = 300
    UPLOAD_REQUEST: Final[int] = 60
    HEALTH_CHECK: Final[int] = 10
    UPSTREAM_SERVICE: Final[int] = 30


# =============================================================================
# PAGINATION
# =============================================================================

class Pagination:
    """Pagination configuration constants"""
    DEFAULT_PAGE_SIZE: Final[int] = 20
    MAX_PAGE_SIZE: Final[int] = 100
    DEFAULT_PAGE: Final[int] = 1


# =============================================================================
# API VERSIONING
# =============================================================================

class ApiVersions:
    """API version identifiers"""
    V1: Final[str] = "v1"
    CURRENT: Final[str] = "v1"


# =============================================================================
# ROUTE PREFIXES
# =============================================================================

class RoutePrefixes:
    """API route prefix constants"""
    API: Final[str] = "/api"
    V1: Final[str] = "/v1"
    CHAT: Final[str] = "/chat"
    ELR: Final[str] = "/elr"
    MEMORIES: Final[str] = "/memories"
    COGNITIVE: Final[str] = "/cognitive"
    HEALTH: Final[str] = "/health"
    METRICS: Final[str] = "/metrics"
    WALLET: Final[str] = "/wallet"


# =============================================================================
# UPSTREAM SERVICES
# =============================================================================

class UpstreamServices:
    """Upstream service identifiers"""
    CORE_AGENT: Final[str] = "core_agent"
    MEMORY_SERVICE: Final[str] = "memory_service"
    COGNITIVE_SERVICE: Final[str] = "cognitive_service"
    SECURITY_SERVICE: Final[str] = "security_service"
    REPORTING_SERVICE: Final[str] = "reporting_service"
