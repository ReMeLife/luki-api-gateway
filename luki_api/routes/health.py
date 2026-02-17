from fastapi import APIRouter, HTTPException, Query, status
from luki_api.config import settings
from luki_api.monitoring.health_monitor import health_monitor, ServiceStatus
from typing import Dict, Any, Optional
from pydantic import BaseModel
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    """Schema for health check response"""
    status: str
    service: str
    version: str
    dependencies: Optional[Dict[str, Any]] = None

    class Config:
        schema_extra = {
            "example": {
                "status": "healthy",
                "service": "luki-api-gateway",
                "version": "0.2.0",
                "dependencies": None,
            }
        }


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    description=(
        "Returns the health status of the API gateway. "
        "Pass ?deep=true to include downstream service checks."
    ),
    responses={
        200: {"description": "Service is healthy"},
        503: {"description": "Service is unhealthy or degraded"},
    },
)
async def health_check(deep: bool = Query(False, description="Run downstream dependency checks")):
    """
    Health check endpoint for the API gateway.

    **Shallow mode** (default): confirms the gateway process is running.

    **Deep mode** (``?deep=true``): additionally checks every registered
    downstream service (core-agent, memory, cognitive, security, etc.)
    via the :class:`HealthMonitor` and reports per-service status.  If any
    dependency is unhealthy the overall status is degraded; a 503 is
    returned only if critical services are down.
    """
    overall_status = "healthy"
    dependencies: Optional[Dict[str, Any]] = None

    if deep:
        logger.debug("Deep health check requested")
        try:
            # Run health checks for all registered services
            await health_monitor.check_all_services()
            report = health_monitor.get_health_report()

            dependencies = report.get("services", {})

            # Derive overall status from downstream health
            svc_statuses = [
                info.get("status", ServiceStatus.UNKNOWN.value)
                for info in dependencies.values()
            ]
            if any(s == ServiceStatus.UNHEALTHY.value for s in svc_statuses):
                overall_status = "degraded"
            elif any(s == ServiceStatus.DEGRADED.value for s in svc_statuses):
                overall_status = "degraded"

        except Exception as exc:
            logger.error("Deep health check failed: %s", exc, exc_info=True)
            overall_status = "degraded"
            dependencies = {"error": str(exc)}
    else:
        logger.debug("Shallow health check requested")

    response_data = {
        "status": overall_status,
        "service": "luki-api-gateway",
        "version": settings.VERSION,
        "dependencies": dependencies,
    }

    if overall_status != "healthy":
        # Return 503 so load balancers can react, but still include
        # diagnostic payload in the body for operators.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response_data,
        )

    return response_data
