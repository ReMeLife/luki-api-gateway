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

class ELRItem(BaseModel):
    id: str
    content: str
    user_id: str
    timestamp: str
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

class ELRQuery(BaseModel):
    user_id: str
    query_text: str
    limit: Optional[int] = 10

class ELRResponse(BaseModel):
    items: List[ELRItem]
    total_count: int

@router.get("/items/{user_id}")
async def get_elr_items(user_id: str, request: Request, 
                       memory_client: MemoryServiceClient = Depends(get_memory_client),
                       limit: int = 20):
    """
    Retrieve ELR items for a specific user
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

@router.post("/items", status_code=status.HTTP_201_CREATED)
async def create_elr_item(item: ELRItem, request: Request,
                         memory_client: MemoryServiceClient = Depends(get_memory_client)):
    """
    Create a new ELR item
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

@router.put("/items/{item_id}")
async def update_elr_item(item_id: str, item: ELRItem, request: Request,
                         memory_client: MemoryServiceClient = Depends(get_memory_client)):
    """
    Update an existing ELR item
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

@router.delete("/items/{item_id}")
async def delete_elr_item(item_id: str, request: Request,
                          memory_client: MemoryServiceClient = Depends(get_memory_client)):
    """
    Delete an ELR item
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

@router.post("/search")
async def search_elr_items(query: ELRQuery, request: Request,
                           memory_client: MemoryServiceClient = Depends(get_memory_client)):
    """
    Search for ELR items based on query text
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
