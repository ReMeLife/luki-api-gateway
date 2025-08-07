"""
Request Tracing Middleware

This module provides request tracing functionality for the API Gateway.
"""
import uuid
from typing import Optional, Callable, Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

def get_request_id(request: Request) -> str:
    """
    Get or generate a request ID for tracing
    
    Args:
        request: The incoming request
        
    Returns:
        A unique request ID string
    """
    # Check if a request ID already exists in headers
    request_id = request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())
    
    # Store in request state for middleware and route handlers to access
    request.state.request_id = request_id
    return request_id

def add_request_id_header(response: Response, request_id: str) -> None:
    """
    Add the request ID to response headers
    
    Args:
        response: The outgoing response
        request_id: The request ID to add
    """
    response.headers["X-Request-ID"] = request_id

class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds a unique request ID to each request
    """
    async def dispatch(self, request: Request, call_next):
        # Generate or get request ID
        request_id = get_request_id(request)
        
        # Process the request
        response = await call_next(request)
        
        # Add request ID to response headers
        add_request_id_header(response, request_id)
        
        return response

# Function to create the middleware for FastAPI app integration
def request_id_middleware():
    """
    Create a request ID middleware class for use with FastAPI app.add_middleware()
    
    Returns:
        The RequestIDMiddleware class (not an instance)
    """
    return RequestIDMiddleware
