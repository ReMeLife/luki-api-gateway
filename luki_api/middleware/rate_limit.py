from fastapi import Request
from starlette.responses import JSONResponse
from luki_api.config import settings
import asyncio
import logging
import time
import redis.asyncio as redis
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Redis client for rate limiting
redis_client: Optional[redis.Redis] = None
_redis_failed: bool = False  # Once True, skip all Redis attempts until restart

# Universal message limit with cooldown window (no tiers on ReMeLife)
MESSAGE_LIMIT = 20  # 20 messages per cooldown window
MESSAGE_WINDOW_SECONDS = 10800  # 3 hours cooldown

# In-memory fallback stores
_daily_message_state: Dict[str, Any] = {}
_rate_limit_store: Dict[str, Any] = {}  # Per-minute rate limit fallback

async def get_redis():
    """Get or create Redis client"""
    global redis_client, _redis_failed
    if _redis_failed:
        return None
    if redis_client is None and settings.REDIS_URL:
        try:
            logger.info(f"Connecting to Redis at {settings.REDIS_URL}")
            redis_client = redis.from_url(
                settings.REDIS_URL,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            # Test connection with hard timeout
            await asyncio.wait_for(redis_client.ping(), timeout=3.0)
            logger.info("Redis connection successful")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {str(e)}. Using in-memory fallback.")
            redis_client = None
            _redis_failed = True
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
            
                    # Per-minute rate limits
            # Authenticated users: 60/min (reasonable for normal usage)
            # Anonymous users: use config value (bot protection)
            rate_limit = 60 if is_authenticated else settings.RATE_LIMIT_REQUESTS_PER_MINUTE
            
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
                # Oldest request determines when capacity frees up
                oldest_scores = await redis_conn.zrange(key, 0, 0, withscores=True)
                if oldest_scores:
                    oldest_time = oldest_scores[0][1]
                    retry_after = max(1, int(time_window - (current_time - oldest_time) + 1))
                else:
                    retry_after = max(1, int(time_window))
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Please try again later."},
                    headers={"Retry-After": str(retry_after)},
                )

        except (redis.RedisError, asyncio.TimeoutError) as e:
            logger.error(f"Redis error in rate limiting: {str(e)}")
            _redis_failed = True
            redis_client = None
            # Fall back to in-memory rate limiting instead of skipping
            rate_limit_response = await in_memory_rate_limit(client_id, current_time, is_authenticated)
            if rate_limit_response is not None:
                return rate_limit_response
    else:
        # Fallback to in-memory rate limiting when Redis is unavailable
        rate_limit_response = await in_memory_rate_limit(client_id, current_time, is_authenticated)
        if rate_limit_response is not None:
            return rate_limit_response
    
    # Continue with request
    response = await call_next(request)
    return response

async def in_memory_rate_limit(client_id: str, current_time: float, is_authenticated: bool = False) -> Optional[JSONResponse]:
    """
    In-memory rate limiting as fallback when Redis is unavailable.
    Returns a JSONResponse if rate limited, None otherwise.
    """
    if client_id not in _rate_limit_store:
        _rate_limit_store[client_id] = {
            "requests": [],
            "last_reset": current_time
        }

    client_data = _rate_limit_store[client_id]

    # Remove old requests outside the time window
    time_window = 60  # 1 minute
    client_data["requests"] = [
        req_time for req_time in client_data["requests"]
        if current_time - req_time < time_window
    ]

    # Per-minute rate limits (matching Redis branch)
    rate_limit = 60 if is_authenticated else settings.RATE_LIMIT_REQUESTS_PER_MINUTE
    if len(client_data["requests"]) >= rate_limit:
        logger.warning(f"Rate limit exceeded for client: {client_id}")
        earliest = min(client_data["requests"]) if client_data["requests"] else current_time
        retry_after = max(1, int(time_window - (current_time - earliest) + 1))
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Please try again later."},
            headers={"Retry-After": str(retry_after)},
        )

    # Add current request to store
    client_data["requests"].append(current_time)
    return None


async def check_message_limit(
    user_id: str,
) -> Optional[Dict[str, Any]]:
    """Check if user has exceeded their message limit (20 per 3-hour window).

    Args:
        user_id: The user's ID

    Returns:
        None if within limits, or a rate_limited dict if exceeded
    """
    if not user_id:
        return {"status": "rate_limited", "message": "Authentication required."}

    redis_conn = await get_redis()
    current_time = time.time()

    if redis_conn:
        try:
            key = f"msg_limit:{user_id}"

            # Get current count and window start from Redis
            data = await redis_conn.hgetall(key)  # type: ignore[misc]

            if data:
                window_start = float(data.get(b"window_start", 0))
                count = int(data.get(b"count", 0))

                # Reset if window expired
                if current_time - window_start >= MESSAGE_WINDOW_SECONDS:
                    count = 0
                    window_start = current_time
                    await redis_conn.hset(key, mapping={"window_start": current_time, "count": 0})  # type: ignore[misc]
                    await redis_conn.expire(key, MESSAGE_WINDOW_SECONDS * 2)
            else:
                count = 0
                window_start = current_time

            if count >= MESSAGE_LIMIT:
                remaining_seconds = MESSAGE_WINDOW_SECONDS - (current_time - window_start)
                remaining_minutes = max(1, int(remaining_seconds / 60))
                remaining_hours = remaining_minutes / 60
                time_display = f"~{int(remaining_hours)} hour{'s' if remaining_hours >= 2 else ''}" if remaining_hours >= 1 else f"~{remaining_minutes} minutes"
                return {
                    "status": "rate_limited",
                    "scope": "message_cooldown",
                    "message": f"You've used all {MESSAGE_LIMIT} messages for this window. Please try again in {time_display}.",
                    "limit": MESSAGE_LIMIT,
                    "used": count,
                    "reset_in_seconds": int(remaining_seconds),
                }

            return None

        except redis.RedisError as e:
            logger.error(f"Redis error checking message limit: {e}")
            # Fall through to in-memory fallback

    # In-memory fallback
    state = _daily_message_state
    user_entry = state.get(user_id)

    if user_entry:
        window_start = user_entry.get("window_start", 0)
        count = user_entry.get("count", 0)

        # Reset if window expired
        if current_time - window_start >= MESSAGE_WINDOW_SECONDS:
            user_entry["window_start"] = current_time
            user_entry["count"] = 0
            count = 0
            window_start = current_time
    else:
        count = 0
        window_start = current_time

    if count >= MESSAGE_LIMIT:
        remaining_seconds = MESSAGE_WINDOW_SECONDS - (current_time - window_start)
        remaining_minutes = max(1, int(remaining_seconds / 60))
        remaining_hours = remaining_minutes / 60
        time_display = f"~{int(remaining_hours)} hour{'s' if remaining_hours >= 2 else ''}" if remaining_hours >= 1 else f"~{remaining_minutes} minutes"
        return {
            "status": "rate_limited",
            "scope": "message_cooldown",
            "message": f"You've used all {MESSAGE_LIMIT} messages for this window. Please try again in {time_display}.",
            "limit": MESSAGE_LIMIT,
            "used": count,
            "reset_in_seconds": int(remaining_seconds),
        }

    return None


async def record_message(user_id: str) -> None:
    """Record a successful AI message for rate limiting tracking.

    Args:
        user_id: The user's ID
    """
    if not user_id:
        return

    redis_conn = await get_redis()
    current_time = time.time()

    if redis_conn:
        try:
            key = f"msg_limit:{user_id}"

            # Get current data
            data = await redis_conn.hgetall(key)  # type: ignore[misc]

            if data:
                window_start = float(data.get(b"window_start", 0))

                # Reset if window expired
                if current_time - window_start >= MESSAGE_WINDOW_SECONDS:
                    await redis_conn.hset(key, mapping={"window_start": current_time, "count": 1})  # type: ignore[misc]
                else:
                    await redis_conn.hincrby(key, "count", 1)  # type: ignore[misc]
            else:
                await redis_conn.hset(key, mapping={"window_start": current_time, "count": 1})  # type: ignore[misc]

            await redis_conn.expire(key, MESSAGE_WINDOW_SECONDS * 2)
            return

        except redis.RedisError as e:
            logger.error(f"Redis error recording message: {e}")
            # Fall through to in-memory fallback

    # In-memory fallback
    state = _daily_message_state
    user_entry = state.get(user_id)

    if user_entry:
        window_start = user_entry.get("window_start", 0)

        # Reset if window expired
        if current_time - window_start >= MESSAGE_WINDOW_SECONDS:
            state[user_id] = {"window_start": current_time, "count": 1}
        else:
            user_entry["count"] = user_entry.get("count", 0) + 1
    else:
        state[user_id] = {"window_start": current_time, "count": 1}


async def get_message_usage(user_id: str) -> Dict[str, Any]:
    """Get current message usage for a user.

    Args:
        user_id: The user's ID

    Returns:
        Dict with usage info: used, limit, reset_in_seconds, remaining
    """
    redis_conn = await get_redis()
    current_time = time.time()
    count = 0
    window_start = current_time

    if redis_conn:
        try:
            key = f"msg_limit:{user_id}"
            data = await redis_conn.hgetall(key)  # type: ignore[misc]

            if data:
                window_start = float(data.get(b"window_start", current_time))
                count = int(data.get(b"count", 0))

                # Reset count if window expired
                if current_time - window_start >= MESSAGE_WINDOW_SECONDS:
                    count = 0
                    window_start = current_time
        except redis.RedisError as e:
            logger.error(f"Redis error getting message usage: {e}")
    else:
        # In-memory fallback
        state = _daily_message_state
        user_entry = state.get(user_id)
        if user_entry:
            window_start = user_entry.get("window_start", current_time)
            count = user_entry.get("count", 0)
            if current_time - window_start >= MESSAGE_WINDOW_SECONDS:
                count = 0

    remaining_seconds = max(0, int(MESSAGE_WINDOW_SECONDS - (current_time - window_start)))

    return {
        "used": count,
        "limit": MESSAGE_LIMIT,
        "reset_in_seconds": remaining_seconds,
        "remaining": max(0, MESSAGE_LIMIT - count),
    }
