"""
Metrics Routes

This module provides API endpoints for metrics collection and monitoring.
"""
from fastapi import APIRouter, Request, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response as FastAPIResponse
from typing import Dict, Any

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
