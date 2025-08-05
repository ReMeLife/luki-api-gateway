from fastapi import Request, HTTPException
from luki_api.config import settings
import logging
import time

logger = logging.getLogger(__name__)

# Simple in-memory rate limiter (would use Redis in production)
rate_limit_store = {}

async def rate_limit_middleware(request: Request, call_next):
    """
    Rate limiting middleware that limits requests per user/IP
    """
    if not settings.RATE_LIMIT_ENABLED:
        return await call_next(request)
    
    # Get client identifier (would be more sophisticated in production)
    if request.client is None:
        client_id = "unknown"
    else:
        client_id = request.client.host
    
    # Get current time
    current_time = time.time()
    
    # Check if client exists in store
    if client_id not in rate_limit_store:
        rate_limit_store[client_id] = {
            "requests": [],
            "last_reset": current_time
        }
    
    client_data = rate_limit_store[client_id]
    
    # Remove old requests outside the time window
    time_window = 60  # 1 minute
    client_data["requests"] = [
        req_time for req_time in client_data["requests"]
        if current_time - req_time < time_window
    ]
    
    # Check if rate limit exceeded
    if len(client_data["requests"]) >= settings.RATE_LIMIT_REQUESTS_PER_MINUTE:
        logger.warning(f"Rate limit exceeded for client: {client_id}")
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later."
        )
    
    # Add current request
    client_data["requests"].append(current_time)
    
    # Continue with request
    response = await call_next(request)
    return response
