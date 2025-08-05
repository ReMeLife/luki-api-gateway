from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from luki_api.config import settings
from typing import Optional
import logging

security = HTTPBearer()
logger = logging.getLogger(__name__)

async def auth_middleware(request: Request, call_next):
    """
    Authentication middleware that validates API keys or JWT tokens
    """
    # Skip auth for health checks and root path
    if request.url.path in ["/health", "/health/", "/"]:
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
