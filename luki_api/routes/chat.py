from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import httpx
import logging
import json
import asyncio
from luki_api.config import settings
from luki_api.clients.agent_client import agent_client, AgentChatRequest
from luki_api.clients.memory_service import MemoryServiceClient, ELRQueryRequest

router = APIRouter()
logger = logging.getLogger(__name__)

class ChatMessage(BaseModel):
    """Schema for chat messages in the LUKi conversation"""
    role: str = Field(
        description="The role of the message sender",
        examples=["user", "assistant"]
    )
    content: str = Field(
        description="The content of the message"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "role": "user",
                "content": "Tell me about my interests in hiking."
            }
        }

class ChatRequest(BaseModel):
    """Schema for chat requests to the LUKi agent"""
    messages: List[ChatMessage] = Field(
        description="List of chat messages in the conversation history"
    )
    user_id: str = Field(
        description="Unique identifier for the user"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional session identifier for continuing conversations"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "messages": [
                    {"role": "user", "content": "Tell me about my interests in hiking."},
                    {"role": "assistant", "content": "Based on your ELR, you enjoy mountain hiking."},
                    {"role": "user", "content": "What gear should I buy?"}
                ],
                "user_id": "user123",
                "session_id": "chat_session_456"
            }
        }

class ChatResponse(BaseModel):
    """Schema for chat responses from the LUKi agent"""
    message: ChatMessage = Field(
        description="The assistant's response message"
    )
    session_id: str = Field(
        description="Session identifier for continuing the conversation"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional metadata about the response such as retrieval sources or confidence"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "message": {
                    "role": "assistant",
                    "content": "Based on your hiking interests, I recommend a good pair of hiking boots, a backpack, and trekking poles for mountain terrain."
                },
                "session_id": "chat_session_456",
                "metadata": {
                    "retrieval_count": 3,
                    "ctx_tokens": 2048,
                    "sources": ["elr_12345", "elr_67890"]
                }
            }
        }

@router.post("", 
         response_model=ChatResponse,
         status_code=status.HTTP_200_OK,
         summary="Chat with LUKi Agent",
         description="Send messages to the LUKi agent and receive personalized responses",
         responses={
             200: {"description": "Successful response from the agent"},
             400: {"description": "Invalid request parameters"},
             401: {"description": "Authentication failed"},
             429: {"description": "Rate limit exceeded"},
             500: {"description": "Agent service error"}
         })
async def chat_endpoint(chat_request: ChatRequest, request: Request):
    """
    Main chat endpoint that communicates with the LUKi core agent
    
    This endpoint processes user messages, retrieves relevant context from the user's 
    Electronic Life Record (ELR), and generates personalized responses using the LUKi agent.
    
    Parameters:
    - **chat_request**: Request object containing messages, user_id, and optional session_id
    
    Returns:
    - **ChatResponse**: Response containing the assistant's message, session ID, and metadata
    
    Raises:
    - **HTTPException 400**: If the request is invalid
    - **HTTPException 401**: If authentication fails
    - **HTTPException 429**: If rate limit is exceeded
    - **HTTPException 500**: If the agent service encounters an error
    """
    logger.info(f"Chat request received for user: {chat_request.user_id}")
    
    try:
        # Validate request
        if not chat_request.messages:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one message is required"
            )
        
        # Get the latest user message
        latest_message = chat_request.messages[-1]
        if latest_message.role != "user":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Latest message must be from user"
            )
        
        # Retrieve memory context from memory service
        memory_context = []
        try:
            memory_client = MemoryServiceClient()
            query_request = ELRQueryRequest(
                user_id=chat_request.user_id,
                query_text=latest_message.content,
                limit=5
            )
            memory_response = await memory_client.search_elr_items(query_request)
            memory_context = memory_response.get("results", [])
            logger.info(f"Retrieved {len(memory_context)} memory items for user {chat_request.user_id}")
        except Exception as e:
            logger.warning(f"Memory retrieval failed for user {chat_request.user_id}: {e}")
            # Continue without memory context

        # Prepare agent request with memory context
        agent_request = AgentChatRequest(
            message=latest_message.content,
            user_id=chat_request.user_id,
            session_id=chat_request.session_id,
            context={
                "conversation_history": [
                    {"role": msg.role, "content": msg.content} 
                    for msg in chat_request.messages[:-1]  # Exclude the latest message
                ],
                "memory_context": memory_context
            }
        )
        
        # Call the core agent
        agent_response = await agent_client.chat(agent_request)
        
        # Format response
        response_message = ChatMessage(
            role="assistant",
            content=agent_response.response
        )
        
        return ChatResponse(
            message=response_message,
            session_id=agent_response.session_id,
            metadata=agent_response.metadata
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except httpx.HTTPStatusError as e:
        logger.error(f"Agent service error: {e.response.status_code}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Agent service unavailable"
        )
    except httpx.RequestError as e:
        logger.error(f"Agent service connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to connect to agent service"
        )
    except Exception as e:
        logger.error(f"Unexpected error in chat endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.post("/stream",
         summary="Streaming Chat with LUKi Agent",
         description="Send messages to the LUKi agent and receive streaming responses for real-time interaction",
         responses={
             200: {"description": "Successful streaming response"},
             400: {"description": "Invalid request parameters"},
             401: {"description": "Authentication failed"},
             429: {"description": "Rate limit exceeded"},
             500: {"description": "Agent service error"}
         })
async def chat_stream_endpoint(chat_request: ChatRequest, request: Request):
    """
    Streaming chat endpoint for real-time responses
    
    This endpoint provides a server-sent events (SSE) stream of tokens from the LUKi agent
    for real-time, token-by-token response rendering in the client interface.
    
    Parameters:
    - **chat_request**: Request object containing messages, user_id, and optional session_id
    
    Returns:
    - **StreamingResponse**: Server-sent events stream of response tokens
    
    Raises:
    - **HTTPException 400**: If the request is invalid
    - **HTTPException 401**: If authentication fails
    - **HTTPException 429**: If rate limit is exceeded
    - **HTTPException 500**: If the agent service encounters an error
    """
    logger.info(f"Streaming chat request received for user: {chat_request.user_id}")
    
    async def generate_stream():
        try:
            # Validate request
            if not chat_request.messages:
                yield f"data: {json.dumps({'error': 'At least one message is required'})}\n\n"
                return
            
            # Get the latest user message
            latest_message = chat_request.messages[-1]
            if latest_message.role != "user":
                yield f"data: {json.dumps({'error': 'Latest message must be from user'})}\n\n"
                return
            
            # Retrieve memory context from memory service for streaming
            memory_context = []
            try:
                memory_client = MemoryServiceClient()
                query_request = ELRQueryRequest(
                    user_id=chat_request.user_id,
                    query_text=latest_message.content,
                    limit=5
                )
                memory_response = await memory_client.search_elr_items(query_request)
                memory_context = memory_response.get("results", [])
                logger.info(f"Retrieved {len(memory_context)} memory items for streaming user {chat_request.user_id}")
            except Exception as e:
                logger.warning(f"Memory retrieval failed for streaming user {chat_request.user_id}: {e}")
                # Continue without memory context

            # Prepare agent request with memory context
            agent_request = AgentChatRequest(
                message=latest_message.content,
                user_id=chat_request.user_id,
                session_id=chat_request.session_id,
                context={
                    "conversation_history": [
                        {"role": msg.role, "content": msg.content} 
                        for msg in chat_request.messages[:-1]
                    ],
                    "memory_context": memory_context
                }
            )
            
            # Stream response from agent
            async for token in agent_client.chat_stream(agent_request):
                yield f"data: {json.dumps({'token': token})}\n\n"
            
            # Send completion signal
            yield f"data: {json.dumps({'done': True})}\n\n"
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Agent service streaming error: {e.response.status_code}")
            yield f"data: {json.dumps({'error': 'Agent service unavailable'})}\n\n"
        except httpx.RequestError as e:
            logger.error(f"Agent service streaming connection error: {e}")
            yield f"data: {json.dumps({'error': 'Unable to connect to agent service'})}\n\n"
        except Exception as e:
            logger.error(f"Unexpected error in streaming endpoint: {e}")
            yield f"data: {json.dumps({'error': 'Internal server error'})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream"
        }
    )
