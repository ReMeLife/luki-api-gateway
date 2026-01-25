"""
Request Correlation Middleware

Generates and propagates correlation/trace IDs across distributed services
for request tracking and distributed tracing.
"""

import logging
import uuid
from typing import Callable
from fastapi import Request, Response
from contextvars import ContextVar

logger = logging.getLogger(__name__)

# Context variable to store trace ID for the current request
trace_id_var: ContextVar[str] = ContextVar('trace_id', default=None)

# Header names for trace propagation
TRACE_ID_HEADER = "X-Trace-ID"
REQUEST_ID_HEADER = "X-Request-ID"


def get_trace_id() -> str:
    """
    Get the current request's trace ID.
    
    Returns:
        str: The current trace ID or empty string if not set
    """
    return trace_id_var.get() or ""


def set_trace_id(trace_id: str) -> None:
    """
    Set the trace ID for the current request.
    
    Args:
        trace_id: The trace ID to set
    """
    trace_id_var.set(trace_id)


async def correlation_middleware(request: Request, call_next: Callable) -> Response:
    """
    Middleware to generate and propagate correlation/trace IDs.
    
    This middleware:
    1. Extracts or generates a trace ID for the request
    2. Stores it in context for logging
    3. Propagates it downstream via response headers
    4. Adds it to all log messages for this request
    
    Args:
        request: The incoming request
        call_next: The next middleware or route handler
    
    Returns:
        Response with trace ID headers
    """
    # Extract or generate trace ID
    trace_id = request.headers.get(TRACE_ID_HEADER) or request.headers.get(REQUEST_ID_HEADER)
    
    if not trace_id:
        trace_id = str(uuid.uuid4())
        logger.debug(f"Generated new trace ID: {trace_id}")
    else:
        logger.debug(f"Received existing trace ID: {trace_id}")
    
    # Store in context for access by route handlers and other middleware
    set_trace_id(trace_id)
    
    # Add trace ID to all log messages for this request
    extra_data = {
        "trace_id": trace_id,
        "path": request.url.path,
        "method": request.method
    }
    
    try:
        # Call next middleware/handler
        response = await call_next(request)
        
        # Add trace ID to response headers
        response.headers[TRACE_ID_HEADER] = trace_id
        response.headers[REQUEST_ID_HEADER] = trace_id  # For compatibility
        
        logger.debug(
            f"Request completed",
            extra={**extra_data, "status_code": response.status_code}
        )
        
        return response
        
    except Exception as e:
        logger.error(
            f"Request failed with exception: {str(e)}",
            extra={**extra_data, "error": str(e)},
            exc_info=True
        )
        raise


class CorrelationContext:
    """Context manager for setting trace ID in synchronous code"""
    
    def __init__(self, trace_id: str):
        self.trace_id = trace_id
        self.token = None
    
    def __enter__(self):
        self.token = trace_id_var.set(self.trace_id)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.token:
            trace_id_var.reset(self.token)
