from fastapi import APIRouter, HTTPException, status
from luki_api.config import settings
from typing import Dict, Any
from pydantic import BaseModel
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

class HealthResponse(BaseModel):
    """Schema for health check response"""
    status: str
    service: str
    version: str
    
    class Config:
        schema_extra = {
            "example": {
                "status": "healthy",
                "service": "luki-api-gateway",
                "version": "0.1.0"
            }
        }

@router.get("/",
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
    Health check endpoint that returns the status of the API gateway
    
    This endpoint is used by monitoring systems and load balancers to check
    if the service is operational. It returns basic service information
    including version and health status.
    
    Returns:
    - **HealthResponse**: Object containing status, service name, and version
    
    Raises:
    - **HTTPException 503**: If the service is unhealthy
    """
    logger.info("Health check requested")
    
    # In a more complete implementation, we might check dependencies
    # like database connections, memory service availability, etc.
    
    return {
        "status": "healthy",
        "service": "luki-api-gateway",
        "version": settings.VERSION
    }
