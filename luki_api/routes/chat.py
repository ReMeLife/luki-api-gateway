from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import httpx
import logging
import json
import asyncio
from luki_api.config import settings

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

@router.post("/", 
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
    
    # In a real implementation, this would call the LUKi core agent
    # For now, we'll simulate a response
    response_message = ChatMessage(
        role="assistant",
        content=f"Hello! I'm LUKi, your AI companion. I've received your message: {chat_request.messages[-1].content}"
    )
    
    return ChatResponse(
        message=response_message,
        session_id=chat_request.session_id or "new-session-id"
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
    
    # This would implement streaming responses in a real scenario
    # For now, we'll just return a standard response with a streaming flag
    response_message = ChatMessage(
        role="assistant",
        content=f"Hello! I'm LUKi, your AI companion. I've received your message: {chat_request.messages[-1].content}"
    )
    
    return {
        "message": response_message,
        "session_id": chat_request.session_id or "new-session-id",
        "streaming": True
    }
