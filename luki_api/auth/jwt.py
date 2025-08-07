"""
JWT Authentication Module

This module provides JWT token authentication functionality for the API Gateway.
"""
import logging
import time
from typing import Dict, Optional
from jose import JWTError, jwt
from pydantic import BaseModel
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from luki_api.config import settings

logger = logging.getLogger(__name__)

# Security scheme for JWT tokens
oauth2_scheme = HTTPBearer()

class TokenData(BaseModel):
    """Schema for JWT token data"""
    sub: str  # User ID
    exp: int  # Expiration timestamp
    iat: Optional[int] = None  # Issued at timestamp
    roles: Optional[list[str]] = None  # User roles
    permissions: Optional[list[str]] = None  # User permissions
    consent_level: Optional[str] = None  # User consent level

class JWTAuth:
    """JWT Authentication handler"""
    
    @staticmethod
    def create_token(data: Dict, expires_delta_minutes: int = 60) -> str:
        """
        Create a new JWT token
        
        Args:
            data: Token data including user ID (sub)
            expires_delta_minutes: Token expiration time in minutes
            
        Returns:
            JWT token string
        """
        if not settings.JWT_SECRET_KEY:
            raise ValueError("JWT_SECRET_KEY not configured")
            
        to_encode = data.copy()
        expire = int(time.time()) + (expires_delta_minutes * 60)
        to_encode.update({
            "exp": expire,
            "iat": int(time.time())
        })
        
        token = jwt.encode(
            to_encode, 
            settings.JWT_SECRET_KEY, 
            algorithm=settings.JWT_ALGORITHM
        )
        return token
    
    @staticmethod
    def verify_token(token: str) -> TokenData:
        """
        Verify a JWT token and extract the token data
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded token data
            
        Raises:
            HTTPException: If token is invalid or expired
        """
        if not settings.JWT_SECRET_KEY:
            raise ValueError("JWT_SECRET_KEY not configured")
            
        try:
            payload = jwt.decode(
                token, 
                settings.JWT_SECRET_KEY, 
                algorithms=[settings.JWT_ALGORITHM]
            )
            
            # Validate required fields
            if "sub" not in payload:
                logger.warning("Token missing 'sub' claim")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token"
                )
                
            # Check if token is expired
            if "exp" in payload and int(time.time()) > payload["exp"]:
                logger.warning("Token expired")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token expired"
                )
                
            return TokenData(**payload)
            
        except JWTError as e:
            logger.warning(f"JWT validation error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        except Exception as e:
            logger.error(f"Unexpected error validating token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error validating token: {str(e)}"
            )

# Dependency to get current user from token
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme)
) -> TokenData:
    """
    Get current user from JWT token
    
    Args:
        credentials: HTTP authorization credentials
        
    Returns:
        Token data containing user information
        
    Raises:
        HTTPException: If token is invalid
    """
    token = credentials.credentials
    return JWTAuth.verify_token(token)
