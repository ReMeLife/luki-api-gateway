"""Memory Service HTTP Client

This module provides a client for interacting with the luki-memory-service API.
"""
import httpx
import logging
import time
import asyncio
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from luki_api.config import settings
# Metrics tracking temporarily disabled to avoid initialization issues
# from luki_api.middleware.metrics import (
#     track_memory_service_request,
#     track_memory_service_latency,
#     track_memory_service_error
# )
from luki_api.middleware.metrics import (
    track_memory_service_request,
    track_memory_service_latency,
    track_memory_service_error,
)

logger = logging.getLogger(__name__)

# Service token cache (module-level)
_token_cache = {
    "token": None,
    "expires_at": None,
    "lock": asyncio.Lock()
}

class ELRItemRequest(BaseModel):
    """Schema for ELR item requests"""
    content: str
    user_id: str
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

class ELRQueryRequest(BaseModel):
    """Schema for ELR query requests"""
    user_id: str
    query: str = Field(default="", min_length=0)  # Allow empty queries to fetch all memories
    k: Optional[int] = 10  # Changed from limit to match Memory Service API

class MemoryServiceError(Exception):
    """Exception raised for errors in memory service communication"""
    def __init__(self, message: str, status_code: Optional[int] = None, 
                 response_data: Optional[Dict[str, Any]] = None):
        self.message = message
        self.status_code = status_code
        self.response_data = response_data
        super().__init__(self.message)

class MemoryServiceClient:
    """HTTP client for interacting with the luki-memory-service API"""
    
    def __init__(self, base_url: Optional[str] = None, timeout: float = 10.0):
        """Initialize the memory service client
        
        Args:
            base_url: Base URL for the memory service API. Defaults to config setting.
            timeout: Timeout for HTTP requests in seconds.
        """
        self.base_url = base_url or settings.MEMORY_SERVICE_URL
        self.timeout = timeout
    
    async def _get_cached_service_token(self) -> Optional[str]:
        """Get service token with caching to reduce API calls
        
        Token is cached for 4 minutes (expires in 5 minutes from Memory Service).
        This reduces auth token generation from every request to ~once per 4 minutes.
        
        Returns:
            Service token string or None if generation fails
        """
        async with _token_cache["lock"]:
            # Check if cached token is still valid
            if _token_cache["token"] and _token_cache["expires_at"]:
                if datetime.now() < _token_cache["expires_at"]:
                    logger.debug("Using cached service token")
                    return _token_cache["token"]
            
            # Generate new token
            try:
                logger.info("Generating new service token (cache expired or missing)")
                async with httpx.AsyncClient() as auth_client:
                    token_response = await auth_client.post(
                        f"{self.base_url.rstrip('/')}/auth/service-token",
                        timeout=self.timeout
                    )
                    if token_response.status_code == 200:
                        token_data = token_response.json()
                        token = token_data["access_token"]
                        
                        # Cache token for 4 minutes (Memory Service tokens expire in 5 minutes)
                        _token_cache["token"] = token
                        _token_cache["expires_at"] = datetime.now() + timedelta(minutes=4)
                        logger.info("Service token cached successfully")
                        
                        return token
            except Exception as e:
                logger.error(f"Failed to generate service token: {e}")
                return None
        
    async def _make_request(
        self, method: str, endpoint: str, 
        data: Optional[Union[Dict[str, Any], BaseModel]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to memory service
        
        Args:
            method: HTTP method (get, post, put, delete)
            endpoint: API endpoint path
            data: Request data payload
            params: URL query parameters
            
        Returns:
            Response data as dictionary
            
        Raises:
            MemoryServiceError: On request failure or error response
        """
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        # Convert Pydantic model to dict if needed
        if isinstance(data, BaseModel):
            data = data.model_dump()
            
        # Track the request to the memory service (disabled)
        # track_memory_service_request(method.upper(), endpoint)
        track_memory_service_request(method.upper(), endpoint)
        start_time = time.time()
        
        # Create service token for authentication (with caching)
        headers = {}
        try:
            token = await self._get_cached_service_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        except Exception as e:
            logger.warning(f"Failed to get service token: {e}. Proceeding without auth.")
        
        try:
            async with httpx.AsyncClient() as client:
                if method.lower() == "get":
                    response = await client.get(url, params=params, headers=headers, timeout=self.timeout)
                elif method.lower() == "post":
                    response = await client.post(url, json=data, headers=headers, timeout=self.timeout)
                elif method.lower() == "put":
                    response = await client.put(url, json=data, headers=headers, timeout=self.timeout)
                elif method.lower() == "delete":
                    response = await client.delete(url, params=params, headers=headers, timeout=self.timeout)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                # Handle non-2xx responses
                response.raise_for_status()
                # Track successful request latency (disabled)
                duration = time.time() - start_time
                # track_memory_service_latency(method.upper(), endpoint, duration)
                track_memory_service_latency(method.upper(), endpoint, duration)
                return response.json()
                
        except httpx.HTTPStatusError as e:
            # Track error with status code (disabled)
            error_type = f"HTTP{e.response.status_code}"
            # track_memory_service_error(method.upper(), endpoint, error_type)
            track_memory_service_error(method.upper(), endpoint, error_type)
            
            try:
                error_data = e.response.json()
                error_msg = error_data.get("detail", str(e))
            except:
                error_data = {}
                error_msg = str(e)
                
            logger.error(f"Memory service HTTP error: {error_msg}")
            raise MemoryServiceError(
                message=error_msg,
                status_code=e.response.status_code,
                response_data=error_data
            )
        except httpx.RequestError as e:
            # Track connection error (disabled)
            error_type = "ConnectionError"
            # track_memory_service_error(method.upper(), endpoint, error_type)
            track_memory_service_error(method.upper(), endpoint, error_type)
            
            logger.error(f"Memory service request failed: {str(e)}")
            raise MemoryServiceError(message=f"Request failed: {str(e)}")
        except Exception as e:
            # Track unexpected errors (disabled)
            error_type = type(e).__name__
            # track_memory_service_error(method.upper(), endpoint, error_type)
            track_memory_service_error(method.upper(), endpoint, error_type)
            
            logger.error(f"Unexpected error in memory service client: {str(e)}")
            raise MemoryServiceError(message=f"Unexpected error: {str(e)}")
            
    # ELR API Methods
    
    async def get_elr_items(self, user_id: str, limit: int = 20) -> Dict[str, Any]:
        """Get ELR items for a user
        
        Args:
            user_id: User ID to get ELR items for
            limit: Maximum number of items to return
            
        Returns:
            Dictionary containing ELR items and metadata
        """
        return await self._make_request(
            "get", 
            f"/api/elr/items/{user_id}",
            params={"limit": limit}
        )
    
    async def create_elr_item(self, item: ELRItemRequest) -> Dict[str, Any]:
        """Create a new ELR item
        
        Args:
            item: ELR item data
            
        Returns:
            Created item data including ID
        """
        return await self._make_request("post", "/api/elr/items", data=item)
    
    async def update_elr_item(self, item_id: str, item: ELRItemRequest) -> Dict[str, Any]:
        """Update an existing ELR item
        
        Args:
            item_id: ID of the item to update
            item: Updated ELR item data
            
        Returns:
            Updated item data
        """
        return await self._make_request("put", f"/api/elr/items/{item_id}", data=item)
    
    async def delete_elr_item(self, item_id: str) -> Dict[str, Any]:
        """Delete an ELR item
        
        Args:
            item_id: ID of the item to delete
            
        Returns:
            Deletion confirmation
        """
        # Call the new delete endpoint in Memory Service
        return await self._make_request("delete", f"/delete/memory/{item_id}")
    
    async def search_elr_items(self, query: Union[ELRQueryRequest, Dict[str, Any]]) -> Dict[str, Any]:
        """Search for ELR items
        
        Args:
            query: Search query parameters
            
        Returns:
            Search results including matched items
        """
        # Convert to dict if it's a Pydantic model
        if isinstance(query, ELRQueryRequest):
            data = query.model_dump()
        else:
            data = query
        return await self._make_request("post", "/search/memories", data=data)
