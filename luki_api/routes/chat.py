from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List
import httpx
import logging
from luki_api.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    user_id: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    message: ChatMessage
    session_id: str

@router.post("/", response_model=ChatResponse)
async def chat_endpoint(chat_request: ChatRequest, request: Request):
    """
    Main chat endpoint that communicates with the LUKi core agent
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

@router.post("/stream")
async def chat_stream_endpoint(chat_request: ChatRequest, request: Request):
    """
    Streaming chat endpoint for real-time responses
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
