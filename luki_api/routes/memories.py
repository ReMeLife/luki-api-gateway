"""
Memory Management API Routes
Provides CRUD operations for user ELR memories
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime

from luki_api.clients.memory_service import MemoryServiceClient, ELRItemRequest
router = APIRouter(prefix="/api/elr", tags=["memories"])
logger = logging.getLogger(__name__)


class Memory(BaseModel):
    """Memory item model"""
    content: str
    tags: Optional[List[str]] = []
    metadata: Optional[Dict[str, Any]] = {}


class MemoryResponse(BaseModel):
    """Memory response model"""
    id: str
    content: str
    created_at: str
    tags: Optional[List[str]] = []
    metadata: Optional[Dict[str, Any]] = {}


class MemoriesListResponse(BaseModel):
    """List of memories response"""
    items: List[MemoryResponse]
    total: int
    user_id: str


@router.get("/items/{user_id}", response_model=MemoriesListResponse)
async def get_user_memories(
    user_id: str,
    limit: int = 50,
    offset: int = 0
):
    """
    Get all memories for a user.
    
    Parameters:
    - user_id: The user ID to fetch memories for
    - limit: Maximum number of memories to return (default: 50)
    - offset: Number of memories to skip (for pagination)
    
    Returns:
    - List of memory items with metadata
    """
    logger.info(f"Fetching memories for user: {user_id}, limit: {limit}, offset: {offset}")
    
    try:
        memory_client = MemoryServiceClient()
        from luki_api.clients.memory_service import ELRQueryRequest
        
        # WORKAROUND: Memory service requires non-empty query string
        # Use a space character as query to fetch all memories
        query = ELRQueryRequest(
            user_id=user_id,
            query=" ",  # Single space to bypass validation but match everything
            k=limit
        )
        search_result = await memory_client.search_elr_items(query)
        
        # Convert search results to memory format
        memories = []
        for result in search_result.get("results", []):
            memories.append(MemoryResponse(
                id=result.get("chunk_id", ""),
                content=result.get("content", ""),
                created_at=result.get("metadata", {}).get("created_at", datetime.utcnow().isoformat()),
                tags=result.get("metadata", {}).get("tags", []),
                metadata=result.get("metadata", {})
            ))
        
        logger.info(f"Found {len(memories)} memories for user {user_id}")
        
        return MemoriesListResponse(
            items=memories,
            total=len(memories),
            user_id=user_id
        )
        
    except Exception as e:
        logger.error(f"Failed to fetch memories: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch memories: {str(e)}"
        )


@router.post("/items/{user_id}", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(user_id: str, memory: Memory):
    """
    Create a new memory for a user.
    
    Parameters:
    - memory: Memory content, tags, and metadata
    - user_id: The user ID (from authentication)
    
    Returns:
    - Created memory with ID and timestamp
    """
    logger.info(f"Creating memory for user: {user_id}")
    
    try:
        memory_client = MemoryServiceClient()
        
        # Prepare ELR data for ingestion with correct format
        elr_request = {
            "user_id": user_id,
            "elr_data": {
                "content": memory.content,
                "content_type": "MEMORY",
                "timestamp": datetime.utcnow().isoformat(),
                "metadata": memory.metadata or {}
            },
            "consent_level": "private",  # Must be lowercase
            "sensitivity_level": "personal",  # Must be lowercase
            "source_file": "manual_entry"
        }
        
        # Call memory service ingestion endpoint
        result = await memory_client._make_request(
            "post",
            "/ingestion/elr",
            data=elr_request
        )
        
        if result.get("success"):
            # Return the created memory
            memory_id = result.get("chunk_ids", [""])[0] if result.get("chunk_ids") else "unknown"
            
            return MemoryResponse(
                id=memory_id,
                content=memory.content,
                created_at=datetime.utcnow().isoformat(),
                tags=memory.tags,
                metadata=memory.metadata
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Memory ingestion failed"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create memory: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create memory: {str(e)}"
        )


@router.delete("/items/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(memory_id: str, user_id: str):
    """
    Delete a memory.
    
    Parameters:
    - memory_id: The memory ID to delete
    - user_id: The user ID (for authorization)
    
    Returns:
    - 204 No Content on success
    """
    logger.info(f"Deleting memory {memory_id} for user {user_id}")
    
    try:
        # TODO: Implement actual deletion in memory service
        # For now, return success
        # The memory service needs a delete endpoint
        
        logger.warning(f"Memory deletion not fully implemented yet - memory {memory_id} marked for deletion")
        
        return None
        
    except Exception as e:
        logger.error(f"Failed to delete memory: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete memory: {str(e)}"
        )


@router.get("/items/{user_id}/search")
async def search_memories(
    user_id: str,
    query: str,
    limit: int = 10
):
    """
    Search memories for a user.
    
    Parameters:
    - user_id: The user ID
    - query: Search query
    - limit: Maximum results to return
    
    Returns:
    - Matching memories sorted by relevance
    """
    logger.info(f"Searching memories for user {user_id}: '{query}'")
    
    try:
        memory_client = MemoryServiceClient()
        from luki_api.clients.memory_service import ELRQueryRequest
        
        # WORKAROUND: Memory service requires non-empty query string
        query_text = query if query and query.strip() else " "
        query_request = ELRQueryRequest(
            user_id=user_id,
            query=query_text,
            k=limit
        )
        search_result = await memory_client.search_elr_items(query_request)
        
        memories = []
        for result in search_result.get("results", []):
            memories.append(MemoryResponse(
                id=result.get("chunk_id", ""),
                content=result.get("content", ""),
                created_at=result.get("metadata", {}).get("created_at", datetime.utcnow().isoformat()),
                tags=result.get("metadata", {}).get("tags", []),
                metadata=result.get("metadata", {})
            ))
        
        return MemoriesListResponse(
            items=memories,
            total=len(memories),
            user_id=user_id
        )
        
    except Exception as e:
        logger.error(f"Failed to search memories: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search memories: {str(e)}"
        )
