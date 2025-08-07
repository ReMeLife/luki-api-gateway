"""
Role Based Access Control (RBAC) Module

This module provides RBAC functionality for the API Gateway.
"""
import logging
from typing import List, Set, Union, Optional, Any
from fastapi import HTTPException, status, Request
from luki_api.auth.jwt import TokenData
from luki_api.auth.api_key import APIKeyData

logger = logging.getLogger(__name__)

class AccessControl:
    """Role Based Access Control handler"""
    
    @staticmethod
    def has_role(auth_data: Union[TokenData, APIKeyData], required_role: str) -> bool:
        """
        Check if user has the required role
        
        Args:
            auth_data: Authentication data from JWT token or API key
            required_role: Role to check for
            
        Returns:
            True if user has the role, False otherwise
        """
        if not auth_data.roles:
            return False
            
        return required_role in auth_data.roles or "admin" in auth_data.roles
    
    @staticmethod
    def has_permission(auth_data: Union[TokenData, APIKeyData], required_permission: str) -> bool:
        """
        Check if user has the required permission
        
        Args:
            auth_data: Authentication data from JWT token or API key
            required_permission: Permission to check for
            
        Returns:
            True if user has the permission, False otherwise
        """
        if not auth_data.permissions:
            return False
            
        # Admin users have all permissions
        if "admin:system" in auth_data.permissions:
            return True
            
        return required_permission in auth_data.permissions
    
    @staticmethod
    def validate_access(auth_data: Union[TokenData, APIKeyData], 
                        required_roles: Optional[List[str]] = None,
                        required_permissions: Optional[List[str]] = None) -> bool:
        """
        Validate that user has the required roles or permissions
        
        Args:
            auth_data: Authentication data from JWT token or API key
            required_roles: List of roles, any one of which is sufficient
            required_permissions: List of permissions, any one of which is sufficient
            
        Returns:
            True if access is granted
            
        Raises:
            HTTPException: If access is denied
        """
        # If no requirements specified, access is granted
        if not required_roles and not required_permissions:
            return True
            
        # Check roles if specified
        if required_roles:
            for role in required_roles:
                if AccessControl.has_role(auth_data, role):
                    return True
                    
        # Check permissions if specified
        if required_permissions:
            for permission in required_permissions:
                if AccessControl.has_permission(auth_data, permission):
                    return True
        
        # If we get here, access is denied
        logger.warning(f"Access denied for user {getattr(auth_data, 'user_id', 'unknown')}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: insufficient privileges"
        )

# Decorator factories for FastAPI endpoints
def requires_roles(*roles):
    """
    Decorator factory to require specific roles
    
    Usage:
    @router.get("/admin")
    @requires_roles("admin")
    async def admin_endpoint(request: Request):
        ...
    """
    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            # Get auth data from request state
            auth_data = getattr(request.state, "auth_data", None)
            if not auth_data:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
                
            # Validate roles
            AccessControl.validate_access(auth_data, required_roles=list(roles))
            
            # If validation passed, call the original function
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator

def requires_permissions(*permissions):
    """
    Decorator factory to require specific permissions
    
    Usage:
    @router.post("/items")
    @requires_permissions("write:items")
    async def create_item(request: Request):
        ...
    """
    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            # Get auth data from request state
            auth_data = getattr(request.state, "auth_data", None)
            if not auth_data:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
                
            # Validate permissions
            AccessControl.validate_access(auth_data, required_permissions=list(permissions))
            
            # If validation passed, call the original function
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator
