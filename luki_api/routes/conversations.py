"""
Conversation Management API Routes
Provides CRUD operations for chat conversation history
"""
from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime
import uuid
import os

try:
    # Supabase is optional: when not installed, we fall back to in-memory storage.
    from supabase import create_client, Client  # type: ignore
except ImportError:  # pragma: no cover - exercised indirectly in tests
    create_client = None  # type: ignore[assignment]
    Client = None  # type: ignore[assignment]

router = APIRouter(prefix="/api/conversations", tags=["conversations"])
logger = logging.getLogger(__name__)

# Initialize Supabase client (if available)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase: Optional[Client] = None  # type: ignore[type-arg]

if SUPABASE_URL and SUPABASE_KEY and create_client is not None:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)  # type: ignore[call-arg]
    logger.info("✅ Supabase client initialized for conversations")
else:
    logger.warning("⚠️ Supabase not configured or supabase package missing - using in-memory storage")


class Message(BaseModel):
    """Chat message model"""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: str


class Conversation(BaseModel):
    """Conversation model"""
    id: str
    user_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int
    preview: Optional[str] = None
    messages: Optional[List[Message]] = []


class ConversationCreate(BaseModel):
    """Create conversation request"""
    title: Optional[str] = "New Conversation"
    first_message: Optional[str] = None


class ConversationsList(BaseModel):
    """List of conversations"""
    conversations: List[Conversation]
    total: int


# In-memory storage for now (TODO: Replace with database)
# Structure: {user_id: {conversation_id: Conversation or dict}}
# Note: Using Any to allow both dict and Conversation objects for compatibility
from typing import Any
conversations_store: Dict[str, Dict[str, Any]] = {}


@router.get("/{user_id}", response_model=ConversationsList)
async def get_user_conversations(
    user_id: str,
    limit: int = 50,
    offset: int = 0
):
    """
    Get all conversations for a user.
    
    Parameters:
    - user_id: The user ID
    - limit: Maximum conversations to return
    - offset: Number to skip (pagination)
    
    Returns:
    - List of conversations with metadata
    """
    logger.info(f"Fetching conversations for user: {user_id}")
    
    try:
        if supabase:
            # Fetch from Supabase
            response = supabase.table("conversations")\
                .select("*")\
                .eq("user_id", user_id)\
                .order("updated_at", desc=True)\
                .range(offset, offset + limit - 1)\
                .execute()
            
            # Get message counts for each conversation
            conversations_list = []
            for conv in response.data:
                msg_count_response = supabase.table("messages")\
                    .select("id", count="exact")\
                    .eq("conversation_id", conv["id"])\
                    .execute()
                
                conversations_list.append(Conversation(
                    id=conv["id"],
                    user_id=conv["user_id"],
                    title=conv.get("title", "New Conversation"),
                    created_at=conv["created_at"],
                    updated_at=conv["updated_at"],
                    message_count=msg_count_response.count or 0,
                    preview=conv.get("preview"),
                    messages=[]
                ))
            
            logger.info(f"Found {len(conversations_list)} conversations for user {user_id} from Supabase")
            
            return ConversationsList(
                conversations=conversations_list,
                total=len(conversations_list)
            )
        else:
            # Fallback to in-memory
            user_conversations = conversations_store.get(user_id, {})
            conversations_list = list(user_conversations.values())
            conversations_list.sort(key=lambda x: x.updated_at, reverse=True)
            paginated = conversations_list[offset:offset + limit]
            
            logger.info(f"Found {len(conversations_list)} conversations for user {user_id} from memory")
            
            return ConversationsList(
                conversations=paginated,
                total=len(conversations_list)
            )
        
    except Exception as e:
        logger.error(f"Failed to fetch conversations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch conversations: {str(e)}"
        )


@router.api_route("/{user_id}/messages/{conversation_id}", methods=["OPTIONS"], include_in_schema=False)
async def options_conversation_messages(request: Request, user_id: str, conversation_id: str):
    """Handle CORS preflight with explicit headers"""
    logger.info(f"🚀 OPTIONS HANDLER HIT! user_id={user_id}, conv_id={conversation_id}")
    logger.info(f"🚀 Origin: {request.headers.get('origin')}")
    logger.info(f"🚀 Access-Control-Request-Headers: {request.headers.get('access-control-request-headers')}")
    
    from fastapi.responses import Response
    
    # Get origin from request
    origin = request.headers.get("origin", "*")
    logger.info(f"🚀 Setting CORS origin to: {origin}")
    
    # Create response with explicit CORS headers (must match main middleware - no credentials)
    headers = {
        "Access-Control-Allow-Origin": origin if origin in [
            "https://chat-interface-ai.netlify.app",
            "http://localhost:3000",
            "http://localhost:3001",
            "https://remelife.com",
            "https://www.remelife.com",
            "https://remelife.app",
            "https://www.remelife.app"
        ] else "https://chat-interface-ai.netlify.app",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
        "Access-Control-Allow-Headers": "*",  # Allow ALL headers
        "Access-Control-Max-Age": "3600",
        "Access-Control-Expose-Headers": "*"
    }
    
    logger.info(f"🚀 Returning OPTIONS with headers: {headers}")
    
    return Response(
        content="",
        status_code=200,
        headers=headers
    )

@router.get("/{user_id}/messages/{conversation_id}")
async def get_conversation_messages(
    request: Request,
    user_id: str,
    conversation_id: str,
    limit: int = 100,
    offset: int = 0
):
    """
    Get all messages from a specific conversation.
    
    Parameters:
    - user_id: The user ID
    - conversation_id: The conversation ID
    - limit: Maximum number of messages to return
    - offset: Number of messages to skip
    
    Returns:
    - List of messages in the conversation
    """
    logger.info(f"📚 ===== GET MESSAGES REQUEST =====")
    logger.info(f"📚 user_id: {user_id}")
    logger.info(f"📚 conversation_id: {conversation_id}")
    logger.info(f"📚 limit: {limit}, offset: {offset}")
    logger.info(f"📚 Request method: {request.method}")
    logger.info(f"📚 Request origin: {request.headers.get('origin', 'NO ORIGIN')}")
    logger.info(f"📚 Has Authorization: {bool(request.headers.get('authorization'))}")
    
    try:
        if supabase:
            # Get messages from Supabase
            logger.info(f"🔍 Querying Supabase messages table for conversation_id={conversation_id}")
            
            response = supabase.table("messages")\
                .select("*")\
                .eq("conversation_id", conversation_id)\
                .order("created_at")\
                .range(offset, offset + limit - 1)\
                .execute()
            
            logger.info(f"📦 Supabase returned {len(response.data)} raw messages")
            if response.data:
                logger.info(f"📦 First message sample: role={response.data[0].get('role')}, content_length={len(response.data[0].get('content', ''))}")
            else:
                logger.warning(f"⚠️ NO MESSAGES FOUND for conversation_id={conversation_id}")
                # Try to find if conversation exists
                conv_check = supabase.table("conversations").select("id, title, message_count").eq("id", conversation_id).execute()
                logger.info(f"🔍 Conversation exists in DB: {len(conv_check.data) > 0}")
                if conv_check.data:
                    logger.info(f"🔍 Conversation details: {conv_check.data[0]}")
            
            messages = []
            for msg in response.data:
                messages.append({
                    "id": msg.get("id"),
                    "role": msg.get("role"),
                    "content": msg.get("content"),
                    "timestamp": msg.get("created_at")
                })
            
            logger.info(f"✅ Returning {len(messages)} messages to client")
            
            # Return data with explicit CORS headers matching preflight
            from fastapi.responses import JSONResponse
            
            response_data = {
                "conversation_id": conversation_id,
                "messages": messages,
                "total": len(messages)
            }
            logger.info(f"📚 Response data: {len(str(response_data))} chars")
            logger.info(f"📚 ===== END GET MESSAGES =====")
            
            # Get origin from request
            origin = request.headers.get("origin", "*")
            
            # Return with explicit CORS headers that match OPTIONS response
            return JSONResponse(
                content=response_data,
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
                    "Access-Control-Allow-Headers": "authorization,content-type",
                    "Access-Control-Expose-Headers": "*"
                }
            )
        else:
            # Fallback to in-memory if Supabase is not available
            user_conversations = conversations_store.get(user_id, {})
            conversation = user_conversations.get(conversation_id)
            
            response_data = {
                "conversation_id": conversation_id,
                "messages": conversation.messages[offset:offset + limit] if conversation else [],
                "total": len(conversation.messages) if conversation else 0
            }
            
            # Return response without manual CORS headers (middleware handles this)
            return response_data
                
    except Exception as e:
        logger.error(f"Failed to fetch messages: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch messages: {str(e)}"
        )


@router.post("/{user_id}", response_model=Conversation, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    user_id: str,
    conversation: ConversationCreate
):
    """
    Create a new conversation.
    
    Parameters:
    - user_id: The user ID
    - conversation: Conversation details
    
    Returns:
    - Created conversation with ID
    """
    logger.info(f"Creating conversation for user: {user_id}")
    
    try:
        conversation_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        
        if supabase:
            # Create in Supabase
            conv_data = {
                "id": conversation_id,
                "user_id": user_id,
                "title": conversation.title or "New Conversation",
                "preview": conversation.first_message[:100] if conversation.first_message else None,
                "created_at": now,
                "updated_at": now
            }
            
            response = supabase.table("conversations").insert(conv_data).execute()
            
            # Add first message if provided
            message_count = 0
            if conversation.first_message:
                msg_data = {
                    "conversation_id": conversation_id,
                    "role": "user",
                    "content": conversation.first_message,
                    "created_at": now
                }
                supabase.table("messages").insert(msg_data).execute()
                message_count = 1
            
            logger.info(f"Created conversation {conversation_id} in Supabase")
            
            return Conversation(
                id=conversation_id,
                user_id=user_id,
                title=conversation.title or "New Conversation",
                created_at=now,
                updated_at=now,
                message_count=message_count,
                preview=conversation.first_message[:100] if conversation.first_message else None,
                messages=[]
            )
        else:
            # Fallback to in-memory
            messages = []
            if conversation.first_message:
                messages.append(Message(
                    role="user",
                    content=conversation.first_message,
                    timestamp=now
                ))
            
            new_conversation = Conversation(
                id=conversation_id,
                user_id=user_id,
                title=conversation.title or "New Conversation",
                created_at=now,
                updated_at=now,
                message_count=len(messages),
                preview=conversation.first_message[:100] if conversation.first_message else None,
                messages=messages
            )
            
            if user_id not in conversations_store:
                conversations_store[user_id] = {}
            
            conversations_store[user_id][conversation_id] = new_conversation
            logger.info(f"Created conversation {conversation_id} in memory")
            
            return new_conversation
        
    except Exception as e:
        logger.error(f"Failed to create conversation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create conversation: {str(e)}"
        )


@router.get("/{user_id}/{conversation_id}", response_model=Conversation)
async def get_conversation(
    user_id: str,
    conversation_id: str
):
    """
    Get a specific conversation with all messages.
    
    Parameters:
    - user_id: The user ID
    - conversation_id: The conversation ID
    
    Returns:
    - Conversation with full message history
    """
    logger.info(f"Fetching conversation {conversation_id} for user {user_id}")
    
    try:
        user_conversations = conversations_store.get(user_id, {})
        conversation = user_conversations.get(conversation_id)
        
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        return conversation
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch conversation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch conversation: {str(e)}"
        )


@router.post("/{user_id}/{conversation_id}/messages", response_model=Conversation)
async def add_message_to_conversation(
    user_id: str,
    conversation_id: str,
    message: Message
):
    """
    Add a message to a conversation.
    
    Parameters:
    - user_id: The user ID
    - conversation_id: The conversation ID
    - message: The message to add
    
    Returns:
    - Updated conversation
    """
    logger.info(f"Adding message to conversation {conversation_id}")
    
    try:
        user_conversations = conversations_store.get(user_id, {})
        conversation = user_conversations.get(conversation_id)
        
        if not conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        # Add message
        if conversation.messages is None:
            conversation.messages = []
        
        conversation.messages.append(message)
        conversation.message_count = len(conversation.messages)
        conversation.updated_at = datetime.utcnow().isoformat()
        
        # Update preview if first user message
        if not conversation.preview and message.role == "user":
            conversation.preview = message.content[:100]
        
        # Update title if it's still default
        if conversation.title == "New Conversation" and message.role == "user":
            conversation.title = message.content[:50] + ("..." if len(message.content) > 50 else "")
        
        logger.info(f"Added message to conversation {conversation_id}, now has {conversation.message_count} messages")
        
        return conversation
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add message: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add message: {str(e)}"
        )


@router.delete("/{user_id}/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    user_id: str,
    conversation_id: str
):
    """
    Delete a conversation.
    
    Parameters:
    - user_id: The user ID
    - conversation_id: The conversation ID
    
    Returns:
    - 204 No Content on success
    """
    logger.info(f"Deleting conversation {conversation_id} for user {user_id}")
    
    try:
        if supabase:
            # Delete from Supabase (messages will cascade delete)
            response = supabase.table("conversations")\
                .delete()\
                .eq("id", conversation_id)\
                .eq("user_id", user_id)\
                .execute()
            
            if not response.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conversation not found"
                )
            
            logger.info(f"Deleted conversation {conversation_id} from Supabase")
        else:
            # Fallback to in-memory
            user_conversations = conversations_store.get(user_id, {})
            
            if conversation_id not in user_conversations:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conversation not found"
                )
            
            del user_conversations[conversation_id]
            logger.info(f"Deleted conversation {conversation_id} from memory")
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete conversation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete conversation: {str(e)}"
        )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_all_conversations(user_id: str):
    """
    Clear all conversations for a user.
    
    Parameters:
    - user_id: The user ID
    
    Returns:
    - 204 No Content on success
    """
    logger.info(f"Clearing all conversations for user {user_id}")
    
    try:
        if user_id in conversations_store:
            del conversations_store[user_id]
        
        logger.info(f"Cleared all conversations for user {user_id}")
        
        return None
        
    except Exception as e:
        logger.error(f"Failed to clear conversations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear conversations: {str(e)}"
        )
