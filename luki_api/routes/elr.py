from fastapi import APIRouter, HTTPException, Request, Depends, status
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging
from luki_api.config import settings
from luki_api.clients.memory_service import (
    MemoryServiceClient,
    MemoryServiceError,
    ELRItemRequest,
    ELRQueryRequest
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Dependency for memory service client
async def get_memory_client():
    client = MemoryServiceClient()
    try:
        yield client
    except Exception as e:
        logger.error(f"Error with memory service client: {str(e)}")
        raise  # Re-raise the exception to ensure proper FastAPI error handling

class ELRItem(BaseModel):
    """Electronic Life Record (ELR) item schema"""
    id: str = ""  # Empty default for creation requests
    content: str
    user_id: str
    timestamp: str = ""  # Empty default for creation requests
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    
    class Config:
        schema_extra = {
            "example": {
                "id": "elr_12345",
                "content": "User enjoys hiking in the mountains",
                "user_id": "user123",
                "timestamp": "2025-08-05T15:30:00Z",
                "tags": ["interests", "outdoor_activities"],
                "metadata": {"source": "user_profile", "confidence": 0.95}
            }
        }

class ELRQuery(BaseModel):
    """Schema for ELR search queries"""
    user_id: str
    query_text: str
    limit: Optional[int] = 10
    
    class Config:
        schema_extra = {
            "example": {
                "user_id": "user123",
                "query_text": "hiking mountains",
                "limit": 5
            }
        }

class ELRResponse(BaseModel):
    """Response schema for ELR item queries"""
    items: List[ELRItem]
    total_count: int
    
    class Config:
        schema_extra = {
            "example": {
                "items": [
                    {
                        "id": "elr_12345",
                        "content": "User enjoys hiking in the mountains",
                        "user_id": "user123",
                        "timestamp": "2025-08-05T15:30:00Z",
                        "tags": ["interests", "outdoor_activities"],
                        "metadata": {"source": "user_profile", "confidence": 0.95}
                    }
                ],
                "total_count": 1
            }
        }

@router.get("/items/{user_id}", 
         response_model=ELRResponse,
         status_code=status.HTTP_200_OK,
         summary="Retrieve ELR Items",
         description="Fetches Electronic Life Record (ELR) items for a specific user from the memory service",
         responses={
             200: {"description": "Successfully retrieved ELR items"},
             404: {"description": "User not found or no items available"},
             500: {"description": "Memory service error"}
         })
async def get_elr_items(user_id: str, request: Request, 
                       memory_client: MemoryServiceClient = Depends(get_memory_client),
                       limit: int = 20):
    """
    Retrieve ELR items for a specific user
    
    Parameters:
    - **user_id**: Unique identifier for the user whose ELR items to retrieve
    - **limit**: Maximum number of items to return (default: 20)
    
    Returns:
    - **ELRResponse**: Object containing list of ELR items and total count
    
    Raises:
    - **HTTPException 404**: If user not found or no items available
    - **HTTPException 500**: If memory service encounters an error
    """
    logger.info(f"Retrieving ELR items for user: {user_id}")
    
    try:
        # Call the memory service
        result = await memory_client.get_elr_items(user_id=user_id, limit=limit)
        return result
    except MemoryServiceError as e:
        logger.error(f"Memory service error: {str(e)}")
        raise HTTPException(
            status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Memory service error: {e.message}"
        )
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )

@router.post("/items", 
          response_model=ELRItem,
          status_code=status.HTTP_201_CREATED,
          summary="Create ELR Item",
          description="Creates a new Electronic Life Record (ELR) item in the memory service",
          responses={
              201: {"description": "ELR item created successfully"},
              400: {"description": "Invalid ELR item data"},
              500: {"description": "Memory service error"}
          })
async def create_elr_item(item: ELRItem, request: Request,
                         memory_client: MemoryServiceClient = Depends(get_memory_client)):
    """
    Create a new ELR item in the memory service
    
    Parameters:
    - **item**: ELR item to create containing content, user_id, and optional tags/metadata
    
    Returns:
    - **ELRItem**: Created ELR item with assigned ID
    
    Raises:
    - **HTTPException 400**: If item data is invalid
    - **HTTPException 500**: If memory service encounters an error
    
    Example:
    ```json
    {
        "content": "User enjoys hiking in the mountains",
        "user_id": "user123",
        "tags": ["interests", "outdoor_activities"],
        "metadata": {"source": "user_profile", "confidence": 0.95}
    }
    ```
    """
    logger.info(f"Creating ELR item for user: {item.user_id}")
    
    try:
        # Create ELRItemRequest from ELRItem
        item_request = ELRItemRequest(
            content=item.content,
            user_id=item.user_id,
            tags=item.tags,
            metadata=item.metadata
        )
        
        # Call the memory service
        result = await memory_client.create_elr_item(item_request)
        return result
    except MemoryServiceError as e:
        logger.error(f"Memory service error: {str(e)}")
        raise HTTPException(
            status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Memory service error: {e.message}"
        )
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )

@router.put("/items/{item_id}",
         response_model=ELRItem,
         status_code=status.HTTP_200_OK,
         summary="Update ELR Item",
         description="Updates an existing Electronic Life Record (ELR) item in the memory service",
         responses={
             200: {"description": "ELR item updated successfully"},
             404: {"description": "ELR item not found"},
             400: {"description": "Invalid ELR item data"},
             500: {"description": "Memory service error"}
         })
async def update_elr_item(item_id: str, item: ELRItem, request: Request,
                         memory_client: MemoryServiceClient = Depends(get_memory_client)):
    """
    Update an existing ELR item in the memory service
    
    Parameters:
    - **item_id**: ID of the ELR item to update
    - **item**: Updated ELR item data
    
    Returns:
    - **ELRItem**: Updated ELR item
    
    Raises:
    - **HTTPException 404**: If item not found
    - **HTTPException 400**: If item data is invalid
    - **HTTPException 500**: If memory service encounters an error
    """
    logger.info(f"Updating ELR item: {item_id}")
    
    try:
        # Create ELRItemRequest from ELRItem
        item_request = ELRItemRequest(
            content=item.content,
            user_id=item.user_id,
            tags=item.tags,
            metadata=item.metadata
        )
        
        # Call the memory service
        result = await memory_client.update_elr_item(item_id, item_request)
        return result
    except MemoryServiceError as e:
        logger.error(f"Memory service error: {str(e)}")
        raise HTTPException(
            status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Memory service error: {e.message}"
        )
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )

@router.delete("/items/{item_id}", 
            status_code=status.HTTP_204_NO_CONTENT,
            summary="Delete ELR Item",
            description="Deletes an Electronic Life Record (ELR) item from the memory service",
            responses={
                204: {"description": "ELR item deleted successfully"},
                404: {"description": "ELR item not found"},
                500: {"description": "Memory service error"}
            })
async def delete_elr_item(item_id: str, request: Request,
                          memory_client: MemoryServiceClient = Depends(get_memory_client)):
    """
    Delete an ELR item from the memory service
    
    Parameters:
    - **item_id**: ID of the ELR item to delete
    
    Returns:
    - No content on success (204)
    
    Raises:
    - **HTTPException 404**: If item not found
    - **HTTPException 500**: If memory service encounters an error
    """
    logger.info(f"Deleting ELR item: {item_id}")
    
    try:
        # Call the memory service
        result = await memory_client.delete_elr_item(item_id)
        return result
    except MemoryServiceError as e:
        logger.error(f"Memory service error: {str(e)}")
        raise HTTPException(
            status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Memory service error: {e.message}"
        )
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )

@router.post("/search",
           response_model=ELRResponse,
           status_code=status.HTTP_200_OK,
           summary="Search ELR Items",
           description="Searches for Electronic Life Record (ELR) items based on query text",
           responses={
               200: {"description": "Search completed successfully"},
               400: {"description": "Invalid search query"},
               500: {"description": "Memory service error"}
           })
async def search_elr_items(query: ELRQuery, request: Request,
                           memory_client: MemoryServiceClient = Depends(get_memory_client)):
    """
    Search for ELR items based on query text
    
    Parameters:
    - **query**: ELR query object containing user_id, query_text, and optional limit
    
    Returns:
    - **ELRResponse**: Object containing list of matching ELR items and total count
    
    Raises:
    - **HTTPException 400**: If query is invalid
    - **HTTPException 500**: If memory service encounters an error
    
    Example:
    ```json
    {
        "user_id": "user123",
        "query_text": "hiking mountains",
        "limit": 5
    }
    ```
    """
    logger.info(f"Searching ELR items for user: {query.user_id}")
    
    try:
        # Create ELRQueryRequest from ELRQuery
        query_request = ELRQueryRequest(
            user_id=query.user_id,
            query_text=query.query_text,
            limit=query.limit
        )
        
        # Call the memory service
        result = await memory_client.search_elr_items(query_request)
        return result
    except MemoryServiceError as e:
        logger.error(f"Memory service error: {str(e)}")
        raise HTTPException(
            status_code=e.status_code or status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Memory service error: {e.message}"
        )
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )
