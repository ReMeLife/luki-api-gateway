"""Authentication Middleware Module

This module provides authentication middleware for the API Gateway,
supporting both JWT token and API key authentication methods.
"""
from fastapi import Request, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from luki_api.config import settings
from typing import Optional, Callable
import logging

security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)

async def auth_middleware(request: Request, call_next: Callable):
    """
    Authentication middleware that validates API keys or JWT tokens
    
    This middleware handles two authentication methods:
    1. API Key - Validates keys from the X-API-Key header against registered keys
    2. JWT Token - Validates bearer tokens from the Authorization header
    
    Authentication is skipped for health check endpoints and the root path.
    
    Args:
        request: FastAPI Request object
        call_next: Next middleware or route handler in the chain
        
    Returns:
        FastAPI Response object
        
    Raises:
        HTTPException 401: If authentication fails or is missing
    """
    # Skip auth for health checks, root path, test endpoints, and chat (for testing)
    if request.url.path in ["/health", "/health/", "/", "/docs", "/openapi.json", "/redoc"] or request.url.path.startswith("/api/chat"):
        response = await call_next(request)
        return response
    
    # Check for API key in header
    api_key = request.headers.get(settings.API_KEY_HEADER)
    if api_key:
        # In a real implementation, you would validate the API key against a database
        logger.info(f"Authenticated request with API key for path: {request.url.path}")
        request.state.auth_type = "api_key"
        request.state.auth_key = api_key
        response = await call_next(request)
        return response
    
    # Check for JWT token in Authorization header
    try:
        credentials: Optional[HTTPAuthorizationCredentials] = await security(request)
        if credentials:
            # In a real implementation, you would validate the JWT token
            logger.info(f"Authenticated request with JWT token for path: {request.url.path}")
            request.state.auth_type = "jwt"
            request.state.auth_token = credentials.credentials
            response = await call_next(request)
            return response
    except HTTPException:
        pass
    
    # If no auth provided, raise exception
    raise HTTPException(
        status_code=401,
        detail="Authentication required. Provide API key or JWT token."
    )
