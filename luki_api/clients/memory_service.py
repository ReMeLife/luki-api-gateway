"""
Memory Service HTTP Client

This module provides a client for interacting with the luki-memory-service API.
"""
import httpx
import logging
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel
from luki_api.config import settings

logger = logging.getLogger(__name__)

class ELRItemRequest(BaseModel):
    """Schema for ELR item requests"""
    content: str
    user_id: str
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

class ELRQueryRequest(BaseModel):
    """Schema for ELR query requests"""
    user_id: str
    query_text: str
    limit: Optional[int] = 10

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
            
        try:
            async with httpx.AsyncClient() as client:
                if method.lower() == "get":
                    response = await client.get(url, params=params, timeout=self.timeout)
                elif method.lower() == "post":
                    response = await client.post(url, json=data, timeout=self.timeout)
                elif method.lower() == "put":
                    response = await client.put(url, json=data, timeout=self.timeout)
                elif method.lower() == "delete":
                    response = await client.delete(url, params=params, timeout=self.timeout)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                # Handle non-2xx responses
                response.raise_for_status()
                return response.json()
                
        except httpx.HTTPStatusError as e:
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
            logger.error(f"Memory service request failed: {str(e)}")
            raise MemoryServiceError(message=f"Request failed: {str(e)}")
        except Exception as e:
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
        return await self._make_request("delete", f"/api/elr/items/{item_id}")
    
    async def search_elr_items(self, query: ELRQueryRequest) -> Dict[str, Any]:
        """Search for ELR items
        
        Args:
            query: Search query parameters
            
        Returns:
            Search results including matched items
        """
        return await self._make_request("post", "/api/elr/search", data=query)
