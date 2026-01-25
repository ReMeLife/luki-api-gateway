"""
Base Service Client

Provides common functionality for all service clients including:
- Circuit breaker integration
- Health monitoring
- Request correlation
- Metrics tracking
"""

import logging
import httpx
from typing import Dict, Any, Optional
from datetime import datetime

from luki_api.monitoring.health_monitor import health_monitor
from luki_api.middleware.circuit_breaker import circuit_breaker_manager
from luki_api.middleware.correlation import get_trace_id
from luki_api.middleware import metrics as metrics_middleware

logger = logging.getLogger(__name__)


class ServiceClient:
    """
    Base class for service clients with integrated observability.
    
    Features:
    - Automatic circuit breaker protection
    - Request/response metrics tracking
    - Trace ID propagation
    - Structured logging
    """
    
    def __init__(
        self,
        service_name: str,
        base_url: str,
        timeout: float = 10.0,
        register_health_check: bool = True
    ):
        """
        Initialize service client.
        
        Args:
            service_name: Name of the service for monitoring
            base_url: Base URL of the service
            timeout: Request timeout in seconds
            register_health_check: Whether to register for health monitoring
        """
        self.service_name = service_name
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.client = None
        
        # Register with health monitor
        if register_health_check:
            health_monitor.register_service(
                name=service_name,
                url=base_url,
                timeout=timeout,
                check_interval=30
            )
            logger.info(f"Registered {service_name} for health monitoring")
    
    async def get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=self.timeout)
        return self.client
    
    async def close(self):
        """Close HTTP client"""
        if self.client:
            await self.client.aclose()
            self.client = None
    
    async def request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> httpx.Response:
        """
        Make HTTP request with circuit breaker and monitoring.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (relative to base_url)
            **kwargs: Additional arguments for httpx.request
        
        Returns:
            httpx.Response
        
        Raises:
            Exception: If circuit is open or request fails
        """
        url = f"{self.base_url}{endpoint}"
        
        # Add trace ID to headers for correlation
        trace_id = get_trace_id()
        headers = kwargs.get("headers", {})
        if trace_id:
            headers["X-Trace-ID"] = trace_id
            headers["X-Request-ID"] = trace_id
        kwargs["headers"] = headers
        
        # Track request metrics
        metrics_middleware.track_memory_service_request(method, endpoint)
        start_time = datetime.utcnow()
        
        # Execute with circuit breaker protection
        async def _make_request():
            client = await self.get_client()
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        
        try:
            response = await circuit_breaker_manager.execute_with_breaker(
                service_name=self.service_name,
                func=_make_request
            )
            
            # Track success metrics
            duration = (datetime.utcnow() - start_time).total_seconds()
            metrics_middleware.track_memory_service_latency(method, endpoint, duration)
            
            logger.debug(
                f"{self.service_name} request succeeded",
                extra={
                    "service": self.service_name,
                    "method": method,
                    "endpoint": endpoint,
                    "status_code": response.status_code,
                    "duration_seconds": round(duration, 3),
                    "trace_id": trace_id
                }
            )
            
            return response
            
        except Exception as e:
            # Track error metrics
            error_type = type(e).__name__
            metrics_middleware.track_memory_service_error(method, endpoint, error_type)
            
            logger.error(
                f"{self.service_name} request failed",
                extra={
                    "service": self.service_name,
                    "method": method,
                    "endpoint": endpoint,
                    "error": str(e),
                    "error_type": error_type,
                    "trace_id": trace_id
                },
                exc_info=True
            )
            raise
    
    async def get(self, endpoint: str, **kwargs) -> httpx.Response:
        """Make GET request"""
        return await self.request("GET", endpoint, **kwargs)
    
    async def post(self, endpoint: str, **kwargs) -> httpx.Response:
        """Make POST request"""
        return await self.request("POST", endpoint, **kwargs)
    
    async def put(self, endpoint: str, **kwargs) -> httpx.Response:
        """Make PUT request"""
        return await self.request("PUT", endpoint, **kwargs)
    
    async def delete(self, endpoint: str, **kwargs) -> httpx.Response:
        """Make DELETE request"""
        return await self.request("DELETE", endpoint, **kwargs)
