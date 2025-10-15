from fastapi import Request, HTTPException
from luki_api.config import settings
import logging
import time
import redis.asyncio as redis
import json
from typing import Optional

logger = logging.getLogger(__name__)

# Redis client for rate limiting
redis_client: Optional[redis.Redis] = None

async def get_redis():
    """Get or create Redis client"""
    global redis_client
    if redis_client is None and settings.REDIS_URL:
        try:
            logger.info(f"Connecting to Redis at {settings.REDIS_URL}")
            redis_client = redis.from_url(settings.REDIS_URL)
            # Test connection
            await redis_client.ping()
            logger.info("Redis connection successful")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {str(e)}")
            redis_client = None
    return redis_client

async def rate_limit_middleware(request: Request, call_next):
    """
    Rate limiting middleware that limits requests per user/IP using Redis
    Higher limits for authenticated users to support background polling.
    """
    # Skip rate limiting for OPTIONS preflight requests
    if request.method == "OPTIONS":
        return await call_next(request)
        
    if not settings.RATE_LIMIT_ENABLED:
        return await call_next(request)
    
    # Check if user is authenticated (has valid auth in request state from auth middleware)
    is_authenticated = hasattr(request.state, 'auth_type') and request.state.auth_type in ['supabase_jwt', 'api_key']
    
    # Get API key from request if available (for per-API-key limits)
    api_key = request.headers.get(settings.API_KEY_HEADER)
    
    # Get client identifier (IP address or API key or user_id)
    if is_authenticated and hasattr(request.state, 'user_id'):
        client_id = f"user:{request.state.user_id}"
    elif api_key:
        client_id = f"apikey:{api_key}"
    elif request.client is not None:
        client_id = f"ip:{request.client.host}"
    else:
        client_id = "unknown"
    
    # Get current time
    current_time = time.time()
    time_window = 60  # 1 minute window in seconds
    
    # Try to use Redis if available
    redis_conn = await get_redis()
    
    if redis_conn:
        # Redis-backed rate limiting
        try:
            # Rate limit key in Redis
            key = f"rate_limit:{client_id}"
            
            # Get limit for this client - very high for authenticated users
            # Authenticated users: 10,000/min (essentially unlimited - ~166 req/sec)
            # Anonymous users: 100/min (bot protection)
            # Polling doesn't use Together AI credits (just database queries)
            rate_limit = 10000 if is_authenticated else settings.RATE_LIMIT_REQUESTS_PER_MINUTE
            
            # Use Redis sorted set for time-based expiry
            # Add current timestamp to sorted set
            await redis_conn.zadd(key, {str(current_time): current_time})
            
            # Remove timestamps older than the time window
            await redis_conn.zremrangebyscore(key, 0, current_time - time_window)
            
            # Count requests in the current window
            count = await redis_conn.zcard(key)
            
            # Set key expiry to ensure cleanup
            await redis_conn.expire(key, time_window * 2)
            
            # Check if rate limit exceeded
            if count > rate_limit:
                logger.warning(f"Rate limit exceeded for client: {client_id}")
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Please try again later."
                )
                
        except redis.RedisError as e:
            logger.error(f"Redis error in rate limiting: {str(e)}")
            # Fall back to allowing the request on Redis errors
            pass
    else:
        # Fallback to in-memory rate limiting when Redis is unavailable
        # This is less scalable but provides a backup mechanism
        await in_memory_rate_limit(client_id, current_time, is_authenticated)
    
    # Continue with request
    response = await call_next(request)
    return response

async def in_memory_rate_limit(client_id: str, current_time: float, is_authenticated: bool = False):
    """
    In-memory rate limiting as fallback when Redis is unavailable
    """
    # Simple in-memory store
    rate_limit_store = {}
    
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
    
    # Check if rate limit exceeded - very high for authenticated users
    rate_limit = 10000 if is_authenticated else settings.RATE_LIMIT_REQUESTS_PER_MINUTE
    if len(client_data["requests"]) >= rate_limit:
        logger.warning(f"Rate limit exceeded for client: {client_id}")
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later."
        )
        
    # Add current request to store
    client_data["requests"].append(current_time)
