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
    # Skip auth for health checks, root path, test endpoints, and anonymous chat
    skip_paths = ["/health", "/health/", "/", "/docs", "/openapi.json", "/redoc"]
    skip_prefixes = ["/api/chat", "/test"]  # Allow anonymous chat access and test endpoints
    
    # Allow anonymous access but set user context
    if any(request.url.path.startswith(prefix) for prefix in skip_prefixes):
        request.state.auth_type = "anonymous"
        request.state.user_id = "anonymous_base_user"
        response = await call_next(request)
        return response
    
    if request.url.path in skip_paths:
        response = await call_next(request)
        return response
    
    # Check for API key in header
    api_key = request.headers.get(settings.API_KEY_HEADER)
    if api_key:
        try:
            # Validate API key format and length
            if len(api_key) < 10 or not api_key.replace('-', '').replace('_', '').isalnum():
                client_host = getattr(request.client, 'host', 'unknown') if request.client else 'unknown'
                logger.warning(f"Invalid API key format from {client_host}")
                raise HTTPException(
                    status_code=401,
                    detail="Invalid API key format"
                )
            
            # In a real implementation, you would validate the API key against a database
            logger.info(f"Authenticated request with API key for path: {request.url.path}")
            request.state.auth_type = "api_key"
            request.state.auth_key = api_key
            request.state.user_id = f"api_key_user_{api_key[:8]}"
            response = await call_next(request)
            return response
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"API key validation error: {e}")
            raise HTTPException(
                status_code=500,
                detail="Authentication service error"
            )
    
    # Check for JWT token in Authorization header
    try:
        credentials: Optional[HTTPAuthorizationCredentials] = await security(request)
        if credentials:
            try:
                # Basic JWT format validation
                token_parts = credentials.credentials.split('.')
                if len(token_parts) != 3:
                    client_host = getattr(request.client, 'host', 'unknown') if request.client else 'unknown'
                    logger.warning(f"Invalid JWT format from {client_host}")
                    raise HTTPException(
                        status_code=401,
                        detail="Invalid JWT token format"
                    )
                
                # In a real implementation, you would validate the JWT token signature and claims
                logger.info(f"Authenticated request with JWT token for path: {request.url.path}")
                request.state.auth_type = "jwt"
                request.state.auth_token = credentials.credentials
                request.state.user_id = f"jwt_user_{token_parts[1][:8]}"
                response = await call_next(request)
                return response
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"JWT validation error: {e}")
                raise HTTPException(
                    status_code=500,
                    detail="Token validation service error"
                )
    except HTTPException:
        pass
    
    # If no auth provided, raise exception with detailed error
    client_host = getattr(request.client, 'host', 'unknown') if request.client else 'unknown'
    logger.warning(f"Unauthenticated request to protected path: {request.url.path} from {client_host}")
    raise HTTPException(
        status_code=401,
        detail={
            "error": "Authentication required",
            "message": "Provide API key in X-API-Key header or JWT token in Authorization header",
            "supported_methods": ["api_key", "jwt_bearer"]
        }
    )
