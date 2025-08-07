"""
Metrics Middleware

This module provides API metrics collection functionality using Prometheus.
"""
import time
from typing import Callable, Dict, Any
from fastapi import Request, Response
from prometheus_client import Counter, Histogram, Gauge
import logging

# Logger for this module
logger = logging.getLogger(__name__)

# Define Prometheus metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total number of HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint'],
    buckets=(0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10, 30, 60)
)

IN_PROGRESS = Gauge(
    'http_requests_in_progress',
    'Number of HTTP requests in progress',
    ['method', 'endpoint']
)

ERROR_COUNT = Counter(
    'http_request_errors_total',
    'Total number of HTTP request errors',
    ['method', 'endpoint', 'error_type']
)

API_RATE_LIMIT_HIT = Counter(
    'api_rate_limit_hits_total',
    'Total number of API rate limit hits',
    ['client_ip']
)

MEMORY_SERVICE_REQUEST_COUNT = Counter(
    'memory_service_requests_total',
    'Total number of requests to Memory Service',
    ['method', 'endpoint']
)

MEMORY_SERVICE_LATENCY = Histogram(
    'memory_service_request_duration_seconds',
    'Memory Service request latency in seconds',
    ['method', 'endpoint'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2.5, 5, 10)
)

MEMORY_SERVICE_ERROR_COUNT = Counter(
    'memory_service_errors_total',
    'Total number of Memory Service errors',
    ['method', 'endpoint', 'error_type']
)

# Track active sessions
ACTIVE_SESSIONS = Gauge(
    'active_user_sessions',
    'Number of currently active user sessions',
)

async def metrics_middleware(request: Request, call_next: Callable) -> Response:
    """
    Middleware for collecting API metrics.
    
    This middleware:
    1. Tracks request counts by method, endpoint, and status code
    2. Measures request latency
    3. Tracks concurrent request count
    4. Counts errors by type
    
    Args:
        request: The incoming request
        call_next: The next middleware or route handler
    
    Returns:
        The response from the next middleware or route handler
    """
    # Extract endpoint and method
    # Get the route path pattern for more stable metrics instead of actual URL with parameters
    route = request.scope.get("route")
    endpoint = request.url.path
    if route and getattr(route, "path", None):
        endpoint = route.path
        
    method = request.method
    
    # Track in-progress requests
    IN_PROGRESS.labels(method=method, endpoint=endpoint).inc()
    
    # Start timer for latency measurement
    start_time = time.time()
    
    try:
        response = await call_next(request)
        
        # Record request latency
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(time.time() - start_time)
        
        # Record request count with status code
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=response.status_code).inc()
        
        return response
    except Exception as e:
        # Record error
        error_type = type(e).__name__
        ERROR_COUNT.labels(method=method, endpoint=endpoint, error_type=error_type).inc()
        # Re-raise the exception to be handled elsewhere
        raise
    finally:
        # Track completed in-progress requests
        IN_PROGRESS.labels(method=method, endpoint=endpoint).dec()

# Functions for instrumenting memory service client
def track_memory_service_request(method: str, endpoint: str) -> None:
    """Track a request to the memory service"""
    MEMORY_SERVICE_REQUEST_COUNT.labels(method=method, endpoint=endpoint).inc()

def track_memory_service_latency(method: str, endpoint: str, duration: float) -> None:
    """Track the latency of a memory service request"""
    MEMORY_SERVICE_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)

def track_memory_service_error(method: str, endpoint: str, error_type: str) -> None:
    """Track an error from the memory service"""
    MEMORY_SERVICE_ERROR_COUNT.labels(method=method, endpoint=endpoint, error_type=error_type).inc()

def track_rate_limit_hit(client_ip: str) -> None:
    """Track when a client hits the rate limit"""
    API_RATE_LIMIT_HIT.labels(client_ip=client_ip).inc()

def track_session_start() -> None:
    """Track when a new user session starts"""
    ACTIVE_SESSIONS.inc()

def track_session_end() -> None:
    """Track when a user session ends"""
    ACTIVE_SESSIONS.dec()
