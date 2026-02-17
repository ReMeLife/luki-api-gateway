"""
Metrics Routes

This module provides API endpoints for metrics collection and monitoring.
"""
from fastapi import APIRouter, Request, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response as FastAPIResponse
from typing import Dict, Any
from luki_api.middleware.cache import cache_manager
from luki_api.monitoring.health_monitor import health_monitor
from luki_api.middleware.circuit_breaker import circuit_breaker_manager

router = APIRouter()

@router.get(
    "/",
    summary="Get Prometheus metrics",
    description="Returns Prometheus-formatted metrics for the API Gateway",
    response_description="Prometheus metrics in text format",
    tags=["metrics"]
)
async def get_metrics() -> FastAPIResponse:
    """
    Get Prometheus metrics endpoint.
    
    This endpoint returns all collected metrics in the Prometheus text format,
    which can be scraped by a Prometheus server.
    
    Returns:
        Response: Prometheus metrics in text format
    """
    metrics_data = generate_latest()
    return FastAPIResponse(
        content=metrics_data,
        media_type=CONTENT_TYPE_LATEST
    )

@router.get(
    "/health",
    summary="Metrics health check",
    description="Simple health check for the metrics subsystem",
    response_description="Health status of the metrics subsystem",
    tags=["metrics"]
)
async def metrics_health() -> Dict[str, Any]:
    """
    Check if the metrics subsystem is healthy.
    
    This endpoint returns a simple status indicating whether
    the metrics collection is operational.
    
    Returns:
        Dict[str, Any]: Health status with ok:true if healthy
    """
    return {"status": "ok", "metrics_system": "operational"}

@router.get(
    "/detailed",
    summary="Get detailed metrics",
    description="Returns comprehensive metrics including cache, health, and circuit breakers",
    response_description="Detailed metrics in JSON format",
    tags=["metrics"]
)
async def get_detailed_metrics() -> Dict[str, Any]:
    """
    Get detailed metrics in JSON format.
    
    Provides comprehensive monitoring data including:
    - Cache statistics (hit rate, size, evictions)
    - Service health status
    - Circuit breaker states
    - Request metrics summary
    
    Returns:
        Dict[str, Any]: Detailed metrics dictionary
    """
    return {
        "cache": {
            "stats": cache_manager.cache.get_stats(),
            "ttl_config": cache_manager.ttl_config
        },
        "health": health_monitor.get_health_report(),
        "circuit_breakers": circuit_breaker_manager.get_all_status(),
        "services": {
            name: {
                "status": service.status.value,
                "last_check": service.last_check.isoformat() if service.last_check else None,
                "response_time_ms": service.response_time_ms,
                "consecutive_failures": service.consecutive_failures
            }
            for name, service in health_monitor.services.items()
        }
    }
