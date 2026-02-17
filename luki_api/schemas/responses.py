"""
Response normalization for LUKi API Gateway
Provides consistent error and success response formatting across all endpoints
"""

from typing import Optional, Dict, Any, List, Union
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class ResponseStatus(str, Enum):
    """Response status types"""
    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"


class ErrorCode(str, Enum):
    """Standardized error codes"""
    # Client errors (4xx)
    INVALID_REQUEST = "INVALID_REQUEST"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    
    # Server errors (5xx)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    GATEWAY_TIMEOUT = "GATEWAY_TIMEOUT"
    DOWNSTREAM_ERROR = "DOWNSTREAM_ERROR"
    
    # Service-specific errors
    AGENT_ERROR = "AGENT_ERROR"
    MEMORY_ERROR = "MEMORY_ERROR"
    MODULE_ERROR = "MODULE_ERROR"
    CONSENT_DENIED = "CONSENT_DENIED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"


class ErrorDetail(BaseModel):
    """Detailed error information"""
    field: Optional[str] = Field(None, description="Field that caused the error")
    message: str = Field(..., description="Error message")
    code: Optional[str] = Field(None, description="Specific error code")


class ErrorResponse(BaseModel):
    """Standardized error response"""
    status: ResponseStatus = ResponseStatus.ERROR
    error: Dict[str, Any] = Field(..., description="Error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    trace_id: Optional[str] = Field(None, description="Request trace ID")
    
    @classmethod
    def from_exception(
        cls,
        error_code: ErrorCode,
        message: str,
        details: Optional[List[ErrorDetail]] = None,
        trace_id: Optional[str] = None,
        status_code: int = 500
    ) -> "ErrorResponse":
        """Create error response from exception"""
        error_dict = {
            "code": error_code.value,
            "message": message,
            "status_code": status_code
        }
        
        if details:
            error_dict["details"] = [d.model_dump() for d in details]
        
        return cls(
            error=error_dict,
            trace_id=trace_id
        )
    
    @classmethod
    def validation_error(
        cls,
        errors: List[Dict[str, Any]],
        trace_id: Optional[str] = None
    ) -> "ErrorResponse":
        """Create validation error response"""
        details = [
            ErrorDetail(
                field=error.get("loc", ["unknown"])[-1],
                message=error.get("msg", "Validation failed"),
                code="validation_error"
            )
            for error in errors
        ]
        
        return cls.from_exception(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Request validation failed",
            details=details,
            trace_id=trace_id,
            status_code=422
        )
    
    @classmethod
    def unauthorized(cls, message: str = "Unauthorized", trace_id: Optional[str] = None) -> "ErrorResponse":
        """Create unauthorized error response"""
        return cls.from_exception(
            error_code=ErrorCode.UNAUTHORIZED,
            message=message,
            trace_id=trace_id,
            status_code=401
        )
    
    @classmethod
    def forbidden(cls, message: str = "Access forbidden", trace_id: Optional[str] = None) -> "ErrorResponse":
        """Create forbidden error response"""
        return cls.from_exception(
            error_code=ErrorCode.FORBIDDEN,
            message=message,
            trace_id=trace_id,
            status_code=403
        )
    
    @classmethod
    def not_found(cls, resource: str, trace_id: Optional[str] = None) -> "ErrorResponse":
        """Create not found error response"""
        return cls.from_exception(
            error_code=ErrorCode.NOT_FOUND,
            message=f"{resource} not found",
            trace_id=trace_id,
            status_code=404
        )
    
    @classmethod
    def rate_limited(cls, retry_after: Optional[int] = None, trace_id: Optional[str] = None) -> "ErrorResponse":
        """Create rate limited error response"""
        message = "Rate limit exceeded"
        if retry_after:
            message += f". Retry after {retry_after} seconds"
        
        return cls.from_exception(
            error_code=ErrorCode.RATE_LIMITED,
            message=message,
            trace_id=trace_id,
            status_code=429
        )
    
    @classmethod
    def internal_error(cls, message: str = "Internal server error", trace_id: Optional[str] = None) -> "ErrorResponse":
        """Create internal error response"""
        return cls.from_exception(
            error_code=ErrorCode.INTERNAL_ERROR,
            message=message,
            trace_id=trace_id,
            status_code=500
        )
    
    @classmethod
    def service_unavailable(cls, service: str, trace_id: Optional[str] = None) -> "ErrorResponse":
        """Create service unavailable error response"""
        return cls.from_exception(
            error_code=ErrorCode.SERVICE_UNAVAILABLE,
            message=f"{service} is temporarily unavailable",
            trace_id=trace_id,
            status_code=503
        )
    
    @classmethod
    def gateway_timeout(cls, service: str, trace_id: Optional[str] = None) -> "ErrorResponse":
        """Create gateway timeout error response"""
        return cls.from_exception(
            error_code=ErrorCode.GATEWAY_TIMEOUT,
            message=f"Request to {service} timed out",
            trace_id=trace_id,
            status_code=504
        )


class SuccessResponse(BaseModel):
    """Standardized success response"""
    status: ResponseStatus = ResponseStatus.SUCCESS
    data: Any = Field(..., description="Response data")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    trace_id: Optional[str] = Field(None, description="Request trace ID")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata")
    
    @classmethod
    def create(
        cls,
        data: Any,
        trace_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> "SuccessResponse":
        """Create success response"""
        return cls(
            data=data,
            trace_id=trace_id,
            metadata=metadata
        )


class PaginatedResponse(BaseModel):
    """Paginated response format"""
    status: ResponseStatus = ResponseStatus.SUCCESS
    data: List[Any] = Field(..., description="Response data items")
    pagination: Dict[str, Any] = Field(..., description="Pagination metadata")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    trace_id: Optional[str] = Field(None, description="Request trace ID")
    
    @classmethod
    def create(
        cls,
        items: List[Any],
        total: int,
        limit: int,
        offset: int,
        trace_id: Optional[str] = None
    ) -> "PaginatedResponse":
        """Create paginated response"""
        has_more = offset + len(items) < total
        
        pagination = {
            "total": total,
            "count": len(items),
            "limit": limit,
            "offset": offset,
            "has_more": has_more
        }
        
        if has_more:
            pagination["next_offset"] = offset + limit
        
        return cls(
            data=items,
            pagination=pagination,
            trace_id=trace_id
        )


class StreamChunk(BaseModel):
    """Streaming response chunk"""
    type: str = Field(..., description="Chunk type (delta, done, error)")
    data: Optional[Dict[str, Any]] = Field(None, description="Chunk data")
    error: Optional[Dict[str, Any]] = Field(None, description="Error if type is error")
    
    @classmethod
    def delta(cls, content: str, metadata: Optional[Dict[str, Any]] = None) -> "StreamChunk":
        """Create delta chunk"""
        return cls(
            type="delta",
            data={"content": content, "metadata": metadata}
        )
    
    @classmethod
    def done(cls, metadata: Optional[Dict[str, Any]] = None) -> "StreamChunk":
        """Create done chunk"""
        return cls(
            type="done",
            data={"metadata": metadata}
        )
    
    @classmethod
    def error(cls, error_code: ErrorCode, message: str) -> "StreamChunk":
        """Create error chunk"""
        return cls(
            type="error",
            error={"code": error_code.value, "message": message}
        )


class ChatResponse(BaseModel):
    """Chat endpoint response"""
    text: str = Field(..., description="Agent response text")
    conversation_id: Optional[str] = Field(None, description="Conversation identifier")
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list, description="Tool calls made")
    sources: List[Dict[str, Any]] = Field(default_factory=list, description="Source citations")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Response metadata")


class MemoryResponse(BaseModel):
    """Memory operation response"""
    memories: List[Dict[str, Any]] = Field(..., description="Memory items")
    count: int = Field(..., description="Number of memories")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Query metadata")


class ActivityResponse(BaseModel):
    """Activity recommendation response"""
    activities: List[Dict[str, Any]] = Field(..., description="Recommended activities")
    count: int = Field(..., description="Number of activities")
    reasoning: Optional[str] = Field(None, description="Recommendation reasoning")


class ReportResponse(BaseModel):
    """Report generation response"""
    report_id: str = Field(..., description="Report identifier")
    content: str = Field(..., description="Report content")
    format: str = Field(..., description="Report format")
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: Optional[Dict[str, Any]] = Field(None, description="Report metadata")


class WalletResponse(BaseModel):
    """Wallet verification response"""
    verified: bool = Field(..., description="Whether wallet is verified")
    wallet_address: str = Field(..., description="Wallet address")
    entitlements: Dict[str, Any] = Field(..., description="User entitlements")
    personas: List[Dict[str, Any]] = Field(default_factory=list, description="Available personas")


class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(..., description="Overall health status")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: Optional[str] = Field(None, description="Service version")
    components: Dict[str, str] = Field(default_factory=dict, description="Component health status")
    uptime_seconds: Optional[float] = Field(None, description="Service uptime")


class MetricsResponse(BaseModel):
    """Metrics endpoint response"""
    metrics: Dict[str, Any] = Field(..., description="Metrics data")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Response type union for type hints
APIResponse = Union[SuccessResponse, ErrorResponse, PaginatedResponse]


class ResponseNormalizer:
    """Utility class for normalizing responses"""
    
    @staticmethod
    def success(data: Any, trace_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create normalized success response"""
        return SuccessResponse.create(data, trace_id, metadata).model_dump()
    
    @staticmethod
    def error(
        error_code: ErrorCode,
        message: str,
        trace_id: Optional[str] = None,
        status_code: int = 500,
        details: Optional[List[ErrorDetail]] = None
    ) -> Dict[str, Any]:
        """Create normalized error response"""
        return ErrorResponse.from_exception(
            error_code, message, details, trace_id, status_code
        ).model_dump()
    
    @staticmethod
    def paginated(
        items: List[Any],
        total: int,
        limit: int,
        offset: int,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create normalized paginated response"""
        return PaginatedResponse.create(items, total, limit, offset, trace_id).model_dump()
    
    @staticmethod
    def chat(
        text: str,
        conversation_id: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        sources: Optional[List[Dict[str, Any]]] = None,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create normalized chat response"""
        response = ChatResponse(
            text=text,
            conversation_id=conversation_id,
            tool_calls=tool_calls or [],
            sources=sources or []
        )
        return SuccessResponse.create(response.model_dump(), trace_id).model_dump()
