"""
Response caching middleware for LUKi API Gateway
Provides intelligent caching for expensive operations
"""

import logging
import hashlib
import json
from typing import Optional, Any, Dict
from datetime import datetime, timedelta
from fastapi import Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class CacheEntry:
    """Represents a cached response"""
    
    def __init__(self, data: Any, ttl_seconds: int = 300):
        self.data = data
        self.created_at = datetime.utcnow()
        self.expires_at = self.created_at + timedelta(seconds=ttl_seconds)
    
    def is_expired(self) -> bool:
        """Check if cache entry has expired"""
        return datetime.utcnow() > self.expires_at
    
    def get_age_seconds(self) -> float:
        """Get age of cache entry in seconds"""
        return (datetime.utcnow() - self.created_at).total_seconds()


class InMemoryCache:
    """Simple in-memory cache implementation"""
    
    def __init__(self, max_size: int = 1000):
        self.cache: Dict[str, CacheEntry] = {}
        self.max_size = max_size
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        entry = self.cache.get(key)
        
        if entry is None:
            self.misses += 1
            return None
        
        if entry.is_expired():
            del self.cache[key]
            self.misses += 1
            return None
        
        self.hits += 1
        return entry.data
    
    def set(self, key: str, value: Any, ttl_seconds: int = 300):
        """Set value in cache"""
        # Evict oldest entries if cache is full
        if len(self.cache) >= self.max_size:
            self._evict_oldest()
        
        self.cache[key] = CacheEntry(value, ttl_seconds)
    
    def delete(self, key: str):
        """Delete value from cache"""
        if key in self.cache:
            del self.cache[key]
    
    def clear(self):
        """Clear all cache entries"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
    
    def _evict_oldest(self):
        """Evict oldest cache entry"""
        if not self.cache:
            return
        
        oldest_key = min(
            self.cache.keys(),
            key=lambda k: self.cache[k].created_at
        )
        del self.cache[oldest_key]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self.hits + self.misses
        hit_rate = self.hits / total_requests if total_requests > 0 else 0
        
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": hit_rate,
            "total_requests": total_requests
        }


class CacheManager:
    """Manages caching for different resource types"""
    
    def __init__(self):
        self.cache = InMemoryCache(max_size=1000)
        
        # TTL configurations for different resource types (in seconds)
        self.ttl_config = {
            "elr_list": 120,        # 2 minutes for ELR lists
            "elr_item": 300,        # 5 minutes for individual ELR items
            "conversation": 60,     # 1 minute for conversations
            "activity": 600,        # 10 minutes for activities
            "report": 300,          # 5 minutes for reports
            "default": 180          # 3 minutes default
        }
    
    def generate_cache_key(
        self,
        path: str,
        user_id: Optional[str] = None,
        query_params: Optional[Dict] = None
    ) -> str:
        """
        Generate cache key from request parameters
        
        Args:
            path: Request path
            user_id: User identifier
            query_params: Query parameters
        
        Returns:
            Cache key string
        """
        key_parts = [path]
        
        if user_id:
            key_parts.append(f"user:{user_id}")
        
        if query_params:
            # Sort params for consistent keys
            sorted_params = sorted(query_params.items())
            params_str = json.dumps(sorted_params, sort_keys=True)
            key_parts.append(f"params:{params_str}")
        
        key_string = "|".join(key_parts)
        
        # Hash for shorter keys
        return hashlib.sha256(key_string.encode()).hexdigest()
    
    def should_cache(self, request: Request) -> bool:
        """
        Determine if request should be cached
        
        Args:
            request: FastAPI request
        
        Returns:
            True if request should be cached
        """
        # Only cache GET requests
        if request.method != "GET":
            return False
        
        # Don't cache health checks, metrics, or docs
        if request.url.path in ["/health", "/metrics", "/docs", "/openapi.json", "/redoc"]:
            return False
        
        # Don't cache if cache-control header says no-cache
        cache_control = request.headers.get("cache-control", "")
        if "no-cache" in cache_control.lower():
            return False
        
        # Cache ELR, conversation, and activity endpoints
        cacheable_paths = ["/api/elr/", "/api/conversations/", "/api/activities/"]
        return any(request.url.path.startswith(path) for path in cacheable_paths)
    
    def get_ttl(self, path: str) -> int:
        """Get TTL for path"""
        if "/elr/" in path:
            if path.endswith("/list") or path.endswith("/timeline"):
                return self.ttl_config["elr_list"]
            return self.ttl_config["elr_item"]
        
        if "/conversations/" in path:
            return self.ttl_config["conversation"]
        
        if "/activities/" in path:
            return self.ttl_config["activity"]
        
        if "/reports/" in path:
            return self.ttl_config["report"]
        
        return self.ttl_config["default"]
    
    def invalidate_user_cache(self, user_id: str):
        """Invalidate all cache entries for a user"""
        # In a simple implementation, we clear all cache
        # In production, use Redis with pattern matching
        keys_to_delete = [
            key for key in self.cache.cache.keys()
            if f"user:{user_id}" in key
        ]
        
        for key in keys_to_delete:
            self.cache.delete(key)
        
        logger.info(f"Invalidated {len(keys_to_delete)} cache entries for user {user_id}")


# Global cache manager
cache_manager = CacheManager()


async def cache_middleware(request: Request, call_next):
    """
    Middleware to cache responses
    
    Caches GET requests for expensive operations
    """
    # Check if request should be cached
    if not cache_manager.should_cache(request):
        return await call_next(request)
    
    # Extract user_id from headers or query params
    user_id = request.headers.get("x-user-id") or request.query_params.get("user_id")
    
    # Generate cache key
    cache_key = cache_manager.generate_cache_key(
        path=request.url.path,
        user_id=user_id,
        query_params=dict(request.query_params)
    )
    
    # Try to get from cache
    cached_data = cache_manager.cache.get(cache_key)
    
    if cached_data is not None:
        logger.debug(
            f"Cache HIT for {request.url.path}",
            extra={"path": request.url.path, "user_id": user_id}
        )
        
        # Return cached response with cache headers
        return JSONResponse(
            content=cached_data,
            headers={
                "X-Cache": "HIT",
                "X-Cache-Key": cache_key[:16]
            }
        )
    
    # Cache miss - call next middleware
    logger.debug(
        f"Cache MISS for {request.url.path}",
        extra={"path": request.url.path, "user_id": user_id}
    )
    
    response = await call_next(request)
    
    # Cache successful responses
    if response.status_code == 200 and isinstance(response, JSONResponse):
        try:
            # Get response body
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            
            # Parse JSON
            data = json.loads(body.decode())
            
            # Store in cache
            ttl = cache_manager.get_ttl(request.url.path)
            cache_manager.cache.set(cache_key, data, ttl_seconds=ttl)
            
            # Return new response with cache headers
            return JSONResponse(
                content=data,
                status_code=response.status_code,
                headers={
                    **dict(response.headers),
                    "X-Cache": "MISS",
                    "X-Cache-TTL": str(ttl)
                }
            )
        
        except Exception as e:
            logger.warning(f"Failed to cache response: {e}")
    
    return response
