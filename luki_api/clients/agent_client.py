"""
Agent Client for LUKi Core Agent Communication

This module provides HTTP client functionality to communicate with the
luki-core-agent service for chat conversations and agent orchestration.
"""

import httpx
import logging
import json
from typing import Dict, List, Optional, Any, AsyncGenerator
from pydantic import BaseModel
from luki_api.config import settings

logger = logging.getLogger(__name__)

class AgentMessage(BaseModel):
    """Message format for agent communication"""
    role: str
    content: str

class AgentChatRequest(BaseModel):
    """Request format for agent chat endpoint"""
    message: str
    user_id: str
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class AgentChatResponse(BaseModel):
    """Response format from agent chat endpoint"""
    response: str
    session_id: str
    metadata: Optional[Dict[str, Any]] = None

class AgentClient:
    """HTTP client for communicating with LUKi core agent service"""
    
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or settings.AGENT_SERVICE_URL
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )
        logger.info(f"AgentClient initialized with base_url: {self.base_url}")
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    async def health_check(self) -> bool:
        """Check if the agent service is healthy"""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Agent health check failed: {e}")
            return False
    
    async def chat(self, request: AgentChatRequest) -> AgentChatResponse:
        """
        Send a chat message to the agent and get a response
        
        Args:
            request: AgentChatRequest containing message and context
            
        Returns:
            AgentChatResponse with agent's reply
            
        Raises:
            httpx.HTTPStatusError: If the agent service returns an error
            httpx.RequestError: If there's a network/connection error
        """
        try:
            logger.info(f"Sending chat request to agent for user: {request.user_id}")
            
            # Prepare the request payload for the core agent
            payload = {
                "message": request.message,
                "user_id": request.user_id,
                "session_id": request.session_id,
                "context": request.context or {}
            }
            
            response = await self.client.post(
                f"{self.base_url}/v1/chat",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            response.raise_for_status()
            response_data = response.json()
            
            logger.info(f"Received response from agent for user: {request.user_id}")
            
            return AgentChatResponse(
                response=response_data.get("response", ""),
                session_id=response_data.get("session_id", request.session_id or "new-session"),
                metadata=response_data.get("metadata", {})
            )
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Agent service HTTP error: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Agent service request error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in agent chat: {e}")
            raise
    
    async def chat_stream(self, request: AgentChatRequest) -> AsyncGenerator[str, None]:
        """
        Send a chat message to the agent and stream the response
        
        Args:
            request: AgentChatRequest containing message and context
            
        Yields:
            str: Streaming response tokens from the agent
            
        Raises:
            httpx.HTTPStatusError: If the agent service returns an error
            httpx.RequestError: If there's a network/connection error
        """
        try:
            logger.info(f"Starting streaming chat request to agent for user: {request.user_id}")
            
            # Prepare the request payload for the core agent
            payload = {
                "message": request.message,
                "user_id": request.user_id,
                "session_id": request.session_id,
                "context": request.context or {},
                "stream": True
            }
            
            async with self.client.stream(
                "POST",
                f"{self.base_url}/v1/chat/stream",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                response.raise_for_status()
                
                async for chunk in response.aiter_text():
                    if chunk.strip():
                        # Parse server-sent events format
                        if chunk.startswith("data: "):
                            data = chunk[6:].strip()
                            if data and data != "[DONE]":
                                try:
                                    parsed_data = json.loads(data)
                                    if "token" in parsed_data:
                                        yield parsed_data["token"]
                                    elif "content" in parsed_data:
                                        yield parsed_data["content"]
                                except json.JSONDecodeError:
                                    # If not JSON, yield the raw data
                                    yield data
                        else:
                            yield chunk
                            
        except httpx.HTTPStatusError as e:
            logger.error(f"Agent service streaming HTTP error: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Agent service streaming request error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in agent streaming chat: {e}")
            raise
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

# Global agent client instance
agent_client = AgentClient()
