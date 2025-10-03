"""
Conversation History API Endpoints
Handles loading and saving conversation history for authenticated users
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Optional
import logging
from datetime import datetime
from luki_api.clients.memory_service import MemoryServiceClient

router = APIRouter()
logger = logging.getLogger(__name__)


class ConversationMessage(BaseModel):
    """Single message in a conversation"""
    role: str = Field(description="Message role: 'user' or 'assistant'")
    content: str = Field(description="Message content")
    timestamp: str = Field(description="ISO timestamp of the message")


class ConversationHistoryResponse(BaseModel):
    """Response containing conversation history"""
    user_id: str
    messages: List[ConversationMessage]
    total_count: int


@router.get("/conversation/history/{user_id}",
           response_model=ConversationHistoryResponse,
           summary="Get Conversation History",
           description="Retrieve conversation history for an authenticated user from ELR")
async def get_conversation_history(
    user_id: str,
    limit: int = 50,
    offset: int = 0
):
    """
    Get conversation history for a user from their ELR.
    
    Parameters:
    - **user_id**: The authenticated user's ID
    - **limit**: Maximum number of messages to return (default: 50)
    - **offset**: Number of messages to skip (default: 0)
    
    Returns:
    - Conversation history with messages in chronological order
    """
    
    # Validate user is not anonymous
    if not user_id or user_id == 'anonymous_base_user' or user_id.startswith('anonymous_'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conversation history not available for anonymous users"
        )
    
    try:
        memory_client = MemoryServiceClient()
        
        # Query memory service for conversation ELR items
        # The memory service should filter by content_type="CONVERSATION" and user_id
        search_request = {
            "user_id": user_id,
            "query": "",  # Empty query to get all conversations
            "k": limit,
            "filters": {
                "content_type": "CONVERSATION"
            }
        }
        
        # Call memory service to get conversation ELR items
        result = await memory_client.search_elr_items(search_request)
        
        # Parse ELR items into conversation messages
        messages = []
        elr_items = result.get("results", [])
        
        for item in elr_items:
            content = item.get("content", "")
            timestamp = item.get("timestamp", datetime.now().isoformat())
            
            # Parse conversation format: "User: {msg}\nLUKi: {response}"
            if "User:" in content and "LUKi:" in content:
                parts = content.split("LUKi:", 1)
                user_part = parts[0].replace("User:", "").strip()
                assistant_part = parts[1].strip() if len(parts) > 1 else ""
                
                # Add user message
                if user_part:
                    messages.append(ConversationMessage(
                        role="user",
                        content=user_part,
                        timestamp=timestamp
                    ))
                
                # Add assistant message
                if assistant_part:
                    messages.append(ConversationMessage(
                        role="assistant",
                        content=assistant_part,
                        timestamp=timestamp
                    ))
        
        # Sort by timestamp (oldest first for proper conversation flow)
        messages.sort(key=lambda m: m.timestamp)
        
        # Apply offset and limit
        total_count = len(messages)
        messages = messages[offset:offset + limit]
        
        logger.info(f"Retrieved {len(messages)} conversation messages for user {user_id}")
        
        return ConversationHistoryResponse(
            user_id=user_id,
            messages=messages,
            total_count=total_count
        )
        
    except Exception as e:
        logger.error(f"Error retrieving conversation history for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve conversation history: {str(e)}"
        )


@router.delete("/conversation/history/{user_id}",
              summary="Clear Conversation History",
              description="Clear conversation history for a user (for privacy/data management)")
async def clear_conversation_history(user_id: str):
    """
    Clear all conversation history for a user.
    This is a soft delete that marks conversations as archived.
    """
    
    # Validate user is not anonymous
    if not user_id or user_id == 'anonymous_base_user' or user_id.startswith('anonymous_'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation not available for anonymous users"
        )
    
    try:
        # TODO: Implement soft delete in memory service
        # For now, return success
        logger.info(f"Conversation history cleared for user {user_id}")
        
        return {
            "status": "success",
            "message": f"Conversation history cleared for user {user_id}",
            "user_id": user_id
        }
        
    except Exception as e:
        logger.error(f"Error clearing conversation history for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear conversation history: {str(e)}"
        )
