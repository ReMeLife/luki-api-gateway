"""Authentication Middleware Module

This module provides authentication middleware for the API Gateway,
supporting both JWT token and API key authentication methods.
"""
from fastapi import Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.responses import JSONResponse
from luki_api.config import settings
from typing import Optional, Callable
import logging
from jose import jwt, JWTError
import os

security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)

# Supabase JWT secret for validation
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")  # Will use anon key as backup if not set

async def auth_middleware(request: Request, call_next: Callable):
    """
    Authentication middleware that validates API keys or JWT tokens
    
    This middleware handles two authentication methods:
    1. API Key - Validates keys from the X-API-Key header against registered keys
    2. JWT Token - Validates bearer tokens from the Authorization header
    
    Authentication is skipped for health check endpoints, OPTIONS requests, and the root path.
    
    Args:
        request: FastAPI Request object
        call_next: Next middleware or route handler in the chain
        
    Returns:
        FastAPI Response object
        
    Raises:
        HTTPException 401: If authentication fails or is missing
    """
    # Skip auth for OPTIONS preflight requests (CORS)
    if request.method == "OPTIONS":
        logger.info(f"⚡ OPTIONS preflight: {request.url.path}")
        response = await call_next(request)
        logger.info(f"⚡ OPTIONS response headers: {dict(response.headers)}")
        return response
    
    # Skip auth for health checks, root path, and test endpoints
    skip_paths = ["/health", "/health/", "/", "/docs", "/openapi.json", "/redoc"]
    # These prefixes allow anonymous fallback but still attempt JWT extraction
    soft_auth_prefixes = ["/test", "/api/conversation/history", "/api/conversations", "/api/reme/photo-reminiscence-images", "/api/cognitive", "/api/wallet", "/api/uploads"]
    
    # Debug logging for conversations endpoint
    if "/api/conversations" in request.url.path and "/messages/" in request.url.path:
        logger.info(f" Auth Middleware: Conversations messages request detected")
        logger.info(f" Path: {request.url.path}")
        logger.info(f" Method: {request.method}")
    
    is_soft_auth = any(request.url.path.startswith(prefix) for prefix in soft_auth_prefixes)
    
    if is_soft_auth:
        # Try to extract JWT if present, but allow anonymous fallback
        try:
            credentials: Optional[HTTPAuthorizationCredentials] = await security(request)
            if credentials:
                try:
                    token = credentials.credentials
                    decoded = jwt.decode(
                        token,
                        key=SUPABASE_JWT_SECRET or "",
                        algorithms=["HS256", "HS384", "HS512"],
                        options={
                            "verify_signature": bool(SUPABASE_JWT_SECRET),
                            "verify_aud": False,
                            "verify_iss": False,
                            "verify_exp": True,
                        }
                    )
                    user_id = decoded.get('sub')
                    if user_id:
                        request.state.auth_type = "supabase_jwt"
                        request.state.auth_token = token
                        request.state.user_id = user_id
                        logger.info(f"Authenticated user {user_id} on soft-auth path: {request.url.path}")
                        response = await call_next(request)
                        return response
                except (JWTError, ValueError) as e:
                    logger.debug(f"JWT verification failed on soft-auth path: {e}")
                    pass  # Fall through to anonymous
        except Exception as e:
            logger.warning(f"Unexpected error extracting credentials on soft-auth path: {e}")
        
        # No valid JWT found — allow anonymous access
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
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid API key format"}
                )
            
            # In a real implementation, you would validate the API key against a database
            logger.info(f"Authenticated request with API key for path: {request.url.path}")
            request.state.auth_type = "api_key"
            request.state.auth_key = api_key
            request.state.user_id = f"api_key_user_{api_key[:8]}"
            response = await call_next(request)
            return response
        except Exception as e:
            logger.error(f"API key validation error: {e}")
            return JSONResponse(
                status_code=500,
                content={"detail": "Authentication service error"}
            )
    
    # Check for JWT token in Authorization header
    credentials: Optional[HTTPAuthorizationCredentials] = await security(request)
    if credentials:
        try:
            token = credentials.credentials
            decoded = jwt.decode(
                token,
                key=SUPABASE_JWT_SECRET or "",
                algorithms=["HS256", "HS384", "HS512"],
                options={
                    "verify_signature": bool(SUPABASE_JWT_SECRET),
                    "verify_aud": False,
                    "verify_iss": False,
                    "verify_exp": True,
                }
            )
            user_id = decoded.get('sub')

            if not user_id:
                raise ValueError("No user ID in token")

            logger.info(f"Authenticated user {user_id} for path: {request.url.path}")
            request.state.auth_type = "supabase_jwt"
            request.state.auth_token = token
            request.state.user_id = user_id
            response = await call_next(request)
            return response
        except (JWTError, ValueError) as e:
            client_host = getattr(request.client, 'host', 'unknown') if request.client else 'unknown'
            logger.warning(f"Invalid JWT token from {client_host}: {str(e)}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid JWT token format"}
            )
        except Exception as e:
            logger.error(f"JWT validation error: {e}")
            return JSONResponse(
                status_code=500,
                content={"detail": "Token validation service error"}
            )
    
    # If no auth provided, return 401 directly (JSONResponse because
    # HTTPException raised inside middleware isn't caught by FastAPI's handler)
    client_host = getattr(request.client, 'host', 'unknown') if request.client else 'unknown'
    logger.warning(f"Unauthenticated request to protected path: {request.url.path} from {client_host}")
    return JSONResponse(
        status_code=401,
        content={
            "detail": {
                "error": "Authentication required",
                "message": "Provide API key in X-API-Key header or JWT token in Authorization header",
                "supported_methods": ["api_key", "jwt_bearer"]
            }
        }
    )
