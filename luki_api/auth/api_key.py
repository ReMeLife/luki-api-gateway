"""
API Key Authentication Module

This module provides API key authentication functionality for the API Gateway.
"""
import logging
from typing import Optional, Dict, Any
from pydantic import BaseModel
from fastapi import Request, HTTPException, status
from luki_api.config import settings

logger = logging.getLogger(__name__)

# In a real implementation, these would be stored in a database
# This is a placeholder for development purposes only
MOCK_API_KEYS = {
    "test-api-key-1": {
        "user_id": "user-1",
        "roles": ["user"],
        "permissions": ["read:elr"],
        "rate_limit": 100
    },
    "test-api-key-2": {
        "user_id": "user-2",
        "roles": ["admin"],
        "permissions": ["read:elr", "write:elr", "admin:system"],
        "rate_limit": 1000
    }
}

class APIKeyData(BaseModel):
    """Schema for API key data"""
    api_key: str
    user_id: str
    roles: list[str] = []
    permissions: list[str] = []
    rate_limit: int = settings.RATE_LIMIT_REQUESTS_PER_MINUTE

class APIKeyAuth:
    """API Key Authentication handler"""
    
    @staticmethod
    def validate_api_key(api_key: str) -> Optional[APIKeyData]:
        """
        Validate an API key and return the associated data
        
        Args:
            api_key: API key to validate
            
        Returns:
            API key data if valid, None otherwise
        """
        # In a production environment, this would query a database
        if api_key in MOCK_API_KEYS:
            key_data = MOCK_API_KEYS[api_key]
            return APIKeyData(api_key=api_key, **key_data)
        return None
    
    @staticmethod
    def get_api_key_from_request(request: Request) -> Optional[str]:
        """
        Extract API key from request headers
        
        Args:
            request: FastAPI request object
            
        Returns:
            API key if present, None otherwise
        """
        return request.headers.get(settings.API_KEY_HEADER)
    
    @staticmethod
    def get_api_key_data(request: Request) -> APIKeyData:
        """
        Get and validate API key data from request
        
        Args:
            request: FastAPI request object
            
        Returns:
            API key data
            
        Raises:
            HTTPException: If API key is missing or invalid
        """
        api_key = APIKeyAuth.get_api_key_from_request(request)
        if not api_key:
            logger.warning("API key missing in request")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key required"
            )
        
        key_data = APIKeyAuth.validate_api_key(api_key)
        if not key_data:
            logger.warning(f"Invalid API key: {api_key[:5]}...")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )
        
        return key_data
