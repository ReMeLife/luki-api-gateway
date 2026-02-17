"""
API versioning and deprecation management for LUKi API Gateway
Manages API versions, deprecation warnings, and backward compatibility
"""

import logging
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, date
from enum import Enum
from dataclasses import dataclass
from fastapi import Request, Response
import re

logger = logging.getLogger(__name__)


class VersionStatus(str, Enum):
    """API version status"""
    CURRENT = "current"         # Current stable version
    SUPPORTED = "supported"     # Supported but not latest
    DEPRECATED = "deprecated"   # Deprecated, will be removed
    SUNSET = "sunset"          # No longer supported


@dataclass
class APIVersion:
    """API version metadata"""
    version: str
    status: VersionStatus
    release_date: date
    deprecation_date: Optional[date] = None
    sunset_date: Optional[date] = None
    changelog_url: Optional[str] = None
    breaking_changes: List[str] = None
    
    def __post_init__(self):
        if self.breaking_changes is None:
            self.breaking_changes = []
    
    def is_active(self) -> bool:
        """Check if version is still active (not sunset)"""
        return self.status != VersionStatus.SUNSET
    
    def days_until_sunset(self) -> Optional[int]:
        """Calculate days until sunset"""
        if self.sunset_date:
            delta = self.sunset_date - date.today()
            return delta.days
        return None
    
    def should_warn_deprecation(self) -> bool:
        """Check if deprecation warning should be shown"""
        return self.status in [VersionStatus.DEPRECATED, VersionStatus.SUNSET]


class APIVersionManager:
    """Manage API versions and deprecation"""
    
    def __init__(self):
        self._versions: Dict[str, APIVersion] = {}
        self._current_version: Optional[str] = None
        self._default_version: str = "v1"
        
        # Version extraction patterns
        self._path_pattern = re.compile(r'^/(v\d+)/.*$')
        self._header_pattern = re.compile(r'^v\d+$')
    
    def register_version(
        self,
        version: str,
        status: VersionStatus,
        release_date: date,
        deprecation_date: Optional[date] = None,
        sunset_date: Optional[date] = None,
        changelog_url: Optional[str] = None,
        breaking_changes: Optional[List[str]] = None
    ):
        """
        Register an API version
        
        Args:
            version: Version identifier (e.g., "v1", "v2")
            status: Version status
            release_date: Release date
            deprecation_date: When version was/will be deprecated
            sunset_date: When version will be/was removed
            changelog_url: URL to changelog
            breaking_changes: List of breaking changes
        """
        api_version = APIVersion(
            version=version,
            status=status,
            release_date=release_date,
            deprecation_date=deprecation_date,
            sunset_date=sunset_date,
            changelog_url=changelog_url,
            breaking_changes=breaking_changes or []
        )
        
        self._versions[version] = api_version
        
        if status == VersionStatus.CURRENT:
            self._current_version = version
        
        logger.info(
            f"Registered API version: {version}",
            extra={
                "version": version,
                "status": status.value,
                "release_date": release_date.isoformat()
            }
        )
    
    def extract_version(self, request: Request) -> str:
        """
        Extract API version from request
        
        Priority:
        1. X-API-Version header
        2. Path prefix (/v1/...)
        3. Default version
        
        Args:
            request: FastAPI request
        
        Returns:
            Version string
        """
        # Check header first
        header_version = request.headers.get("X-API-Version")
        if header_version and self._header_pattern.match(header_version):
            if header_version in self._versions:
                return header_version
            else:
                logger.warning(
                    f"Unknown version in header: {header_version}",
                    extra={"requested_version": header_version}
                )
        
        # Check path
        path = request.url.path
        match = self._path_pattern.match(path)
        if match:
            path_version = match.group(1)
            if path_version in self._versions:
                return path_version
        
        # Return default
        return self._default_version
    
    def get_version_info(self, version: str) -> Optional[APIVersion]:
        """Get information about a specific version"""
        return self._versions.get(version)
    
    def get_all_versions(self) -> Dict[str, APIVersion]:
        """Get all registered versions"""
        return self._versions.copy()
    
    def get_current_version(self) -> Optional[str]:
        """Get current version identifier"""
        return self._current_version
    
    def validate_version(self, version: str) -> bool:
        """Check if version is valid and active"""
        version_info = self._versions.get(version)
        if not version_info:
            return False
        return version_info.is_active()
    
    def get_deprecation_warning(self, version: str) -> Optional[Dict[str, Any]]:
        """
        Get deprecation warning for version if applicable
        
        Args:
            version: Version to check
        
        Returns:
            Warning dict or None
        """
        version_info = self._versions.get(version)
        if not version_info or not version_info.should_warn_deprecation():
            return None
        
        warning = {
            "message": f"API version {version} is {version_info.status.value}",
            "status": version_info.status.value,
            "current_version": self._current_version
        }
        
        if version_info.deprecation_date:
            warning["deprecated_on"] = version_info.deprecation_date.isoformat()
        
        if version_info.sunset_date:
            warning["sunset_date"] = version_info.sunset_date.isoformat()
            days_until = version_info.days_until_sunset()
            if days_until is not None:
                warning["days_until_sunset"] = days_until
        
        if version_info.changelog_url:
            warning["changelog_url"] = version_info.changelog_url
        
        if version_info.breaking_changes:
            warning["breaking_changes"] = version_info.breaking_changes
        
        return warning
    
    def add_version_headers(self, response: Response, version: str):
        """
        Add version-related headers to response
        
        Args:
            response: FastAPI response
            version: API version used
        """
        response.headers["X-API-Version"] = version
        
        if self._current_version:
            response.headers["X-API-Current-Version"] = self._current_version
        
        # Add deprecation warning headers
        warning = self.get_deprecation_warning(version)
        if warning:
            response.headers["Warning"] = (
                f'299 - "API version {version} is {warning["status"]}"'
            )
            
            if "sunset_date" in warning:
                response.headers["Sunset"] = warning["sunset_date"]
            
            if "changelog_url" in warning:
                response.headers["Link"] = f'<{warning["changelog_url"]}>; rel="deprecation"'


# Global version manager instance
_version_manager: Optional[APIVersionManager] = None


def get_version_manager() -> APIVersionManager:
    """Get the global API version manager"""
    global _version_manager
    if _version_manager is None:
        _version_manager = APIVersionManager()
        _initialize_versions(_version_manager)
    return _version_manager


def _initialize_versions(manager: APIVersionManager):
    """Initialize default API versions"""
    # Register v1 (current)
    manager.register_version(
        version="v1",
        status=VersionStatus.CURRENT,
        release_date=date(2025, 1, 1),
        changelog_url="https://docs.luki.ai/changelog/v1"
    )
    
    logger.info("Initialized API version manager with default versions")


async def version_middleware(request: Request, call_next: Callable) -> Response:
    """
    Middleware to handle API versioning
    
    Args:
        request: FastAPI request
        call_next: Next middleware/handler
    
    Returns:
        Response with version headers
    """
    manager = get_version_manager()
    
    # Extract version from request
    version = manager.extract_version(request)
    
    # Validate version
    if not manager.validate_version(version):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "INVALID_API_VERSION",
                    "message": f"API version '{version}' is not supported",
                    "current_version": manager.get_current_version()
                }
            }
        )
    
    # Store version in request state for access in routes
    request.state.api_version = version
    
    # Log deprecated version usage
    version_info = manager.get_version_info(version)
    if version_info and version_info.status == VersionStatus.DEPRECATED:
        logger.warning(
            f"Request using deprecated API version",
            extra={
                "version": version,
                "path": request.url.path,
                "method": request.method,
                "days_until_sunset": version_info.days_until_sunset()
            }
        )
    
    # Call next handler
    response = await call_next(request)
    
    # Add version headers
    manager.add_version_headers(response, version)
    
    return response


def require_version(min_version: str):
    """
    Decorator to require minimum API version for endpoint
    
    Args:
        min_version: Minimum required version
    
    Example:
        @router.get("/advanced-feature")
        @require_version("v2")
        async def advanced_feature():
            ...
    """
    def decorator(func: Callable) -> Callable:
        async def wrapper(request: Request, *args, **kwargs):
            current_version = getattr(request.state, "api_version", "v1")
            
            # Simple numeric comparison (v1 < v2 < v3)
            current_num = int(current_version[1:])
            min_num = int(min_version[1:])
            
            if current_num < min_num:
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "code": "VERSION_TOO_LOW",
                            "message": f"This endpoint requires API version {min_version} or higher",
                            "current_version": current_version,
                            "required_version": min_version
                        }
                    }
                )
            
            return await func(request, *args, **kwargs)
        
        return wrapper
    
    return decorator
