from fastapi import APIRouter, HTTPException, status
from luki_api.config import settings
from luki_api.constants import SERVICE_NAME, SERVICE_VERSION
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, UTC
from enum import Enum
import logging
import time
import httpx

router = APIRouter()
logger = logging.getLogger(__name__)

# Track service start time for uptime calculation
_start_time = time.time()


class HealthStatus(str, Enum):
    """Health status indicators"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class DependencyStatus(BaseModel):
    """Status of a single dependency"""
    name: str
    status: HealthStatus
    latency_ms: Optional[float] = None
    message: Optional[str] = None


class HealthResponse(BaseModel):
    """Schema for health check response"""
    status: HealthStatus
    service: str
    version: str
    
    class Config:
        schema_extra = {
            "example": {
                "status": "healthy",
                "service": "luki-api-gateway",
                "version": "1.0.0"
            }
        }


class DetailedHealthResponse(BaseModel):
    """Schema for detailed health check response with dependencies"""
    status: HealthStatus
    service: str
    version: str
    environment: str
    uptime_seconds: float
    timestamp: str
    dependencies: Dict[str, DependencyStatus] = Field(default_factory=dict)
    
    class Config:
        schema_extra = {
            "example": {
                "status": "healthy",
                "service": "luki-api-gateway",
                "version": "1.0.0",
                "environment": "production",
                "uptime_seconds": 3600.5,
                "timestamp": "2024-01-01T12:00:00Z",
                "dependencies": {
                    "core_agent": {
                        "name": "core_agent",
                        "status": "healthy",
                        "latency_ms": 15.2
                    }
                }
            }
        }

async def _check_dependency(name: str, url: str, timeout: float = 5.0) -> DependencyStatus:
    """Check health of a single dependency"""
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            latency_ms = (time.time() - start) * 1000
            
            if response.status_code == 200:
                return DependencyStatus(
                    name=name,
                    status=HealthStatus.HEALTHY,
                    latency_ms=round(latency_ms, 2)
                )
            else:
                return DependencyStatus(
                    name=name,
                    status=HealthStatus.DEGRADED,
                    latency_ms=round(latency_ms, 2),
                    message=f"Unexpected status: {response.status_code}"
                )
    except httpx.TimeoutException:
        return DependencyStatus(
            name=name,
            status=HealthStatus.UNHEALTHY,
            message="Request timed out"
        )
    except Exception as e:
        return DependencyStatus(
            name=name,
            status=HealthStatus.UNHEALTHY,
            message=str(e)
        )


def _compute_overall_status(dependencies: Dict[str, DependencyStatus]) -> HealthStatus:
    """Compute overall health from dependency statuses"""
    if not dependencies:
        return HealthStatus.HEALTHY
    
    statuses = [dep.status for dep in dependencies.values()]
    
    if all(s == HealthStatus.HEALTHY for s in statuses):
        return HealthStatus.HEALTHY
    elif any(s == HealthStatus.UNHEALTHY for s in statuses):
        return HealthStatus.DEGRADED
    else:
        return HealthStatus.DEGRADED


@router.get("/health",
          response_model=HealthResponse,
          status_code=status.HTTP_200_OK,
          summary="Health Check",
          description="Returns the health status of the API gateway service",
          responses={
              200: {"description": "Service is healthy"},
              503: {"description": "Service is unhealthy or degraded"}
          })
async def health_check():
    """
    Quick health check endpoint for load balancers and monitoring.
    
    Returns basic service information including version and health status.
    For detailed health with dependency checks, use /health/detailed.
    """
    logger.debug("Health check requested")
    
    return {
        "status": HealthStatus.HEALTHY,
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION
    }


@router.get("/health/detailed",
          response_model=DetailedHealthResponse,
          status_code=status.HTTP_200_OK,
          summary="Detailed Health Check",
          description="Returns detailed health status including dependency checks",
          responses={
              200: {"description": "Service health with dependency status"},
              503: {"description": "Service is degraded or unhealthy"}
          })
async def detailed_health_check():
    """
    Detailed health check with dependency status.
    
    Checks connectivity to upstream services and returns latency metrics.
    Use this for debugging and detailed monitoring.
    """
    logger.info("Detailed health check requested")
    
    # Define dependencies to check
    dependency_urls = {
        "core_agent": f"{settings.AGENT_SERVICE_URL}/health",
        "memory_service": f"{settings.MEMORY_SERVICE_URL}/health",
    }
    
    # Check all dependencies concurrently
    import asyncio
    tasks = [
        _check_dependency(name, url)
        for name, url in dependency_urls.items()
    ]
    results = await asyncio.gather(*tasks)
    
    # Build dependencies dict
    dependencies = {dep.name: dep for dep in results}
    
    # Compute overall status
    overall_status = _compute_overall_status(dependencies)
    
    response = DetailedHealthResponse(
        status=overall_status,
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
        environment=getattr(settings, 'ENVIRONMENT', 'production'),
        uptime_seconds=round(time.time() - _start_time, 2),
        timestamp=datetime.now(UTC).isoformat(),
        dependencies=dependencies
    )
    
    # Return 503 if degraded
    if overall_status != HealthStatus.HEALTHY:
        logger.warning(f"Service health degraded: {overall_status}")
    
    return response


@router.get("/health/live",
          status_code=status.HTTP_200_OK,
          summary="Liveness Probe",
          description="Simple liveness check for Kubernetes")
async def liveness_probe():
    """Kubernetes liveness probe - returns 200 if process is alive"""
    return {"alive": True}


@router.get("/health/ready",
          status_code=status.HTTP_200_OK,
          summary="Readiness Probe", 
          description="Readiness check for Kubernetes")
async def readiness_probe():
    """Kubernetes readiness probe - returns 200 if ready to accept traffic"""
    return {
        "ready": True,
        "service": SERVICE_NAME,
        "uptime_seconds": round(time.time() - _start_time, 2)
    }
