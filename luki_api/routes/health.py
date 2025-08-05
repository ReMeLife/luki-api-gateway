from fastapi import APIRouter, HTTPException
from luki_api.config import settings
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/")
async def health_check():
    """
    Health check endpoint that returns the status of the API gateway
    """
    logger.info("Health check requested")
    return {
        "status": "healthy",
        "service": "luki-api-gateway",
        "version": "0.1.0"
    }
