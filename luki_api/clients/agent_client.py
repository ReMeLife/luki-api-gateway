
"""
Agent Client for LUKi Core Agent Communication

This module provides HTTP client functionality to communicate with the
luki-core-agent service for chat conversations and agent orchestration.
"""

import httpx
import logging
import json
import time
import uuid
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


class AgentPhotoReminiscenceImageRequest(BaseModel):
    """Request format for photo reminiscence image generation"""
    user_id: str
    activity_title: Optional[str] = None
    answers: List[str]
    n: Optional[int] = 1
    account_tier: Optional[str] = "free"  # free, plus, pro - determines image generation limits

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
            timeout=httpx.Timeout(settings.AGENT_SERVICE_TIMEOUT),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)
        )
        logger.info(f"AgentClient initialized with base_url: {self.base_url}")
        logger.info(f"Agent service timeout: {settings.AGENT_SERVICE_TIMEOUT}s")
    
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
        req_id = uuid.uuid4().hex[:8]
        url = f"{self.base_url}/v1/chat"
        try:
            logger.info(
                f"[AgentClient.chat] req_id={req_id} user_id={request.user_id} "
                f"url={url} timeout={self.client.timeout}"
            )

            # Prepare the request payload for the core agent
            payload = {
                "message": request.message,
                "user_id": request.user_id,
                "session_id": request.session_id,
                "context": request.context or {}
            }

            start = time.monotonic()
            response = await self.client.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "LUKi-API-Gateway/0.2.0"
                }
            )
            elapsed_ms = (time.monotonic() - start) * 1000

            logger.info(
                f"[AgentClient.chat] req_id={req_id} completed in {elapsed_ms:.1f}ms "
                f"with status={response.status_code}"
            )

            response.raise_for_status()
            response_data = response.json()

            logger.info(f"[AgentClient.chat] req_id={req_id} received response for user: {request.user_id}")

            return AgentChatResponse(
                response=response_data.get("response", ""),
                session_id=response_data.get("session_id", request.session_id or "new-session"),
                metadata=response_data.get("metadata", {})
            )

        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response is not None else "unknown"
            text = e.response.text if e.response is not None else "<no body>"
            logger.error(
                f"[AgentClient.chat] req_id={req_id} HTTPStatusError status={status}: {text}"
            )
            raise
        except httpx.RequestError as e:
            req = getattr(e, "request", None)
            req_url = getattr(req, "url", None)
            logger.error(
                f"[AgentClient.chat] req_id={req_id} RequestError type={type(e).__name__} "
                f"url={req_url} detail={e}"
            )
            raise
        except Exception as e:
            logger.error(f"[AgentClient.chat] req_id={req_id} Unexpected error in agent chat: {e}")
            raise
    
    async def photo_reminiscence_images(
        self, request: AgentPhotoReminiscenceImageRequest
    ) -> Dict[str, Any]:
        """Call the core agent to generate images for the Photo Reminiscence activity."""
        try:
            payload = request.dict()
            logger.info(
                "Sending photo reminiscence image request to agent for user: %s",
                request.user_id,
            )
            response = await self.client.post(
                f"{self.base_url}/v1/reme/photo-reminiscence-images",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "LUKi-API-Gateway/0.2.0",
                },
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                "Agent service HTTP error (photo reminiscence images): %s - %s",
                e.response.status_code,
                e.response.text,
            )
            raise
        except httpx.RequestError as e:
            logger.error(
                "Agent service request error (photo reminiscence images): %s", e
            )
            raise
        except Exception as e:
            logger.error(
                "Unexpected error in agent photo reminiscence images call: %s", e
            )
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
                headers={
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                    "User-Agent": "LUKi-API-Gateway/0.2.0"
                }
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
