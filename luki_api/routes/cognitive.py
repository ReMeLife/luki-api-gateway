"""
Cognitive Module Routes

Proxies requests to the cognitive module for Life Story Recording
and other cognitive services.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import httpx

from ..config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cognitive", tags=["cognitive"])

# Request/Response models for Life Story
class StartLifeStoryRequest(BaseModel):
    user_id: str

class ContinueLifeStoryRequest(BaseModel):
    user_id: str
    session_id: str
    response_text: str
    skip_phase: bool = False
    approximate_date: Optional[str] = None

class FinishLifeStoryRequest(BaseModel):
    user_id: str
    session_id: str


async def _proxy_to_cognitive(
    method: str,
    path: str,
    json_body: Optional[dict] = None,
    params: Optional[dict] = None,
) -> dict:
    """Helper to proxy requests to the cognitive module."""
    url = f"{settings.COGNITIVE_SERVICE_URL}{path}"
    
    try:
        async with httpx.AsyncClient(timeout=settings.COGNITIVE_SERVICE_TIMEOUT) as client:
            if method == "GET":
                response = await client.get(url, params=params)
            elif method == "POST":
                response = await client.post(url, json=json_body)
            elif method == "DELETE":
                response = await client.delete(url, params=params)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            # Forward the response status and body
            if response.status_code >= 400:
                logger.warning(
                    "Cognitive module returned error: status=%d path=%s",
                    response.status_code,
                    path,
                )
                try:
                    detail = response.json()
                except Exception:
                    detail = response.text
                raise HTTPException(
                    status_code=response.status_code,
                    detail=detail,
                )
            
            return response.json()
            
    except httpx.TimeoutException:
        logger.error("Timeout calling cognitive module: %s", path)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Cognitive service timed out",
        )
    except httpx.RequestError as e:
        logger.error("Error calling cognitive module: %s - %s", path, str(e))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to reach cognitive service",
        )


# Life Story Recording Endpoints

@router.post("/life-story/start")
async def start_life_story(request: StartLifeStoryRequest):
    """
    Start or resume a life story recording session.
    
    Proxies to the cognitive module's /life-story/start endpoint.
    """
    logger.info("Starting life story session for user: %s...", request.user_id[:8])
    return await _proxy_to_cognitive(
        method="POST",
        path="/life-story/start",
        json_body={"user_id": request.user_id},
    )


@router.post("/life-story/continue")
async def continue_life_story(request: ContinueLifeStoryRequest):
    """
    Continue a life story recording session with a new response.
    
    Proxies to the cognitive module's /life-story/continue endpoint.
    """
    logger.info(
        "Continuing life story session: %s... for user: %s...",
        request.session_id[:8],
        request.user_id[:8],
    )
    return await _proxy_to_cognitive(
        method="POST",
        path="/life-story/continue",
        json_body={
            "user_id": request.user_id,
            "session_id": request.session_id,
            "response_text": request.response_text,
            "skip_phase": request.skip_phase,
            "approximate_date": request.approximate_date,
        },
    )


@router.post("/life-story/finish-early")
async def finish_life_story_early(request: FinishLifeStoryRequest):
    """
    Finish a life story session early, saving whatever chapters have been recorded.
    
    Proxies to the cognitive module's /life-story/finish-early endpoint.
    """
    logger.info(
        "Finishing life story session early: %s... for user: %s...",
        request.session_id[:8],
        request.user_id[:8],
    )
    return await _proxy_to_cognitive(
        method="POST",
        path="/life-story/finish-early",
        json_body={
            "user_id": request.user_id,
            "session_id": request.session_id,
        },
    )


@router.get("/life-story/sessions/{user_id}")
async def get_life_story_sessions(user_id: str, include_chunks: bool = False):
    """
    Get all life story sessions for a user.
    
    Proxies to the cognitive module's /life-story/sessions/{user_id} endpoint.
    """
    logger.info("Getting life story sessions for user: %s...", user_id[:8])
    return await _proxy_to_cognitive(
        method="GET",
        path=f"/life-story/sessions/{user_id}",
        params={"include_chunks": str(include_chunks).lower()},
    )


@router.delete("/life-story/sessions/{session_id}")
async def delete_life_story_session(session_id: str, user_id: str):
    """
    Delete a life story session.
    
    Proxies to the cognitive module's /life-story/sessions/{session_id} endpoint.
    """
    logger.info(
        "Deleting life story session: %s... for user: %s...",
        session_id[:8],
        user_id[:8],
    )
    return await _proxy_to_cognitive(
        method="DELETE",
        path=f"/life-story/sessions/{session_id}",
        params={"user_id": user_id},
    )


@router.get("/life-story/phases")
async def get_life_story_phases():
    """
    Get all available life story phases.
    
    Proxies to the cognitive module's /life-story/phases endpoint.
    """
    return await _proxy_to_cognitive(
        method="GET",
        path="/life-story/phases",
    )
