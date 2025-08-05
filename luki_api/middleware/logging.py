"""
Request Logging Middleware

This module provides request logging and tracing functionality for the API Gateway.
"""
import logging
import time
import uuid
from typing import Optional, Dict, Any
from fastapi import Request, Response
import json

logger = logging.getLogger(__name__)

class RequestLogContext:
    """
    Context manager for request logging that measures execution time and
    maintains request context information.
    """
    def __init__(
        self,
        request: Request,
        correlation_id: Optional[str] = None,
        log_body: bool = False
    ):
        self.request = request
        self.start_time = time.time()
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.log_body = log_body
        self.context = {}
        
    async def __aenter__(self):
        # Add correlation ID to request state
        self.request.state.correlation_id = self.correlation_id
        
        # Log the incoming request
        method = self.request.method
        url = str(self.request.url)
        client_host = getattr(self.request.client, "host", "unknown")
        client_port = getattr(self.request.client, "port", "unknown")
        
        # Extract headers (without sensitive info)
        headers = dict(self.request.headers)
        # Remove sensitive headers
        for sensitive in ["authorization", "cookie", "x-api-key"]:
            if sensitive in headers:
                headers[sensitive] = "[REDACTED]"
        
        # Build log context
        self.context = {
            "correlation_id": self.correlation_id,
            "request": {
                "method": method,
                "url": url,
                "client_host": client_host,
                "client_port": client_port,
                "headers": headers
            }
        }
        
        # Log request body if enabled (and not a multipart form)
        if self.log_body and "multipart/form-data" not in self.request.headers.get("content-type", ""):
            try:
                body = await self.request.body()
                if body:
                    try:
                        # Try to parse as JSON for better logging
                        body_json = json.loads(body)
                        self.context["request"]["body"] = body_json
                    except:
                        # If not JSON, log as string with truncation
                        body_str = body.decode("utf-8", errors="replace")
                        if len(body_str) > 1000:  # truncate long bodies
                            body_str = body_str[:1000] + "..."
                        self.context["request"]["body"] = body_str
            except Exception as e:
                logger.warning(f"Failed to read request body: {str(e)}")
        
        # Log the request
        logger.info(
            f"Request {method} {url} from {client_host}:{client_port}",
            extra={"context": self.context}
        )
        
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Calculate execution time
        execution_time = time.time() - self.start_time
        self.context["execution_time_ms"] = round(execution_time * 1000, 2)
        
        # Log any exceptions
        if exc_type is not None:
            self.context["error"] = {
                "type": exc_type.__name__,
                "message": str(exc_val)
            }
            logger.error(
                f"Request failed: {exc_type.__name__}: {str(exc_val)}",
                extra={"context": self.context},
                exc_info=(exc_type, exc_val, exc_tb)
            )
        else:
            # Log successful completion
            logger.info(
                f"Request completed in {self.context['execution_time_ms']}ms",
                extra={"context": self.context}
            )

async def request_logging_middleware(request: Request, call_next):
    """
    Middleware to log all requests and responses with correlation IDs
    """
    # Check for existing correlation ID in headers
    correlation_id = request.headers.get("X-Correlation-ID")
    
    # Create logging context
    async with RequestLogContext(request, correlation_id=correlation_id) as log_ctx:
        # Process the request
        try:
            response = await call_next(request)
            
            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = log_ctx.correlation_id
            
            # Log response info
            log_ctx.context["response"] = {
                "status_code": response.status_code
            }
            
            return response
            
        except Exception as e:
            # Log unhandled exceptions
            logger.error(
                f"Unhandled exception: {str(e)}",
                extra={"context": log_ctx.context},
                exc_info=True
            )
            
            # Re-raise the exception for FastAPI to handle
            raise
