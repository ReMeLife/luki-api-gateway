"""
Request validation middleware for LUKi API Gateway
Provides input sanitization and validation for all incoming requests
"""

import logging
import re
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when request validation fails"""
    pass


class RequestValidator:
    """Validates and sanitizes incoming requests"""
    
    # Patterns for detecting potential injection attacks
    INJECTION_PATTERNS = [
        r'<script[^>]*>.*?</script>',  # XSS
        r'javascript:',  # JavaScript protocol
        r'on\w+\s*=',  # Event handlers
        r'<iframe[^>]*>',  # Iframes
        r'eval\s*\(',  # Eval calls
        r'expression\s*\(',  # CSS expressions
        r'import\s+',  # Import statements
        r'__import__',  # Python imports
        r'exec\s*\(',  # Exec calls
    ]
    
    # Maximum lengths for different field types
    MAX_LENGTHS = {
        'user_id': 256,
        'message': 8192,
        'conversation_id': 256,
        'memory_id': 256,
        'title': 512,
        'description': 2048,
        'content': 32768,
    }
    
    @classmethod
    def validate_user_id(cls, user_id: str) -> str:
        """
        Validate user ID format
        
        Args:
            user_id: User identifier
        
        Returns:
            Validated user ID
        
        Raises:
            ValidationError: If user ID is invalid
        """
        if not user_id:
            raise ValidationError("user_id is required")
        
        if len(user_id) > cls.MAX_LENGTHS['user_id']:
            raise ValidationError(f"user_id exceeds maximum length of {cls.MAX_LENGTHS['user_id']}")
        
        # Allow alphanumeric, hyphens, underscores, and @ for email-based IDs
        if not re.match(r'^[a-zA-Z0-9@._-]+$', user_id):
            raise ValidationError("user_id contains invalid characters")
        
        return user_id
    
    @classmethod
    def validate_message(cls, message: str) -> str:
        """
        Validate and sanitize message content
        
        Args:
            message: User message
        
        Returns:
            Sanitized message
        
        Raises:
            ValidationError: If message is invalid
        """
        if not message:
            raise ValidationError("message is required")
        
        if len(message) > cls.MAX_LENGTHS['message']:
            raise ValidationError(f"message exceeds maximum length of {cls.MAX_LENGTHS['message']}")
        
        # Check for injection patterns
        for pattern in cls.INJECTION_PATTERNS:
            if re.search(pattern, message, re.IGNORECASE):
                logger.warning(
                    f"Potential injection attempt detected in message",
                    extra={"pattern": pattern}
                )
                raise ValidationError("message contains potentially unsafe content")
        
        # Basic sanitization - remove null bytes
        message = message.replace('\x00', '')
        
        return message.strip()
    
    @classmethod
    def validate_conversation_id(cls, conversation_id: str) -> str:
        """Validate conversation ID format"""
        if not conversation_id:
            raise ValidationError("conversation_id is required")
        
        if len(conversation_id) > cls.MAX_LENGTHS['conversation_id']:
            raise ValidationError(f"conversation_id exceeds maximum length")
        
        # UUIDs or alphanumeric with hyphens
        if not re.match(r'^[a-zA-Z0-9-]+$', conversation_id):
            raise ValidationError("conversation_id contains invalid characters")
        
        return conversation_id
    
    @classmethod
    def sanitize_dict(cls, data: Dict[str, Any], max_depth: int = 5) -> Dict[str, Any]:
        """
        Recursively sanitize dictionary values
        
        Args:
            data: Dictionary to sanitize
            max_depth: Maximum recursion depth
        
        Returns:
            Sanitized dictionary
        """
        if max_depth <= 0:
            return {}
        
        sanitized = {}
        for key, value in data.items():
            # Sanitize key
            if not isinstance(key, str):
                continue
            
            safe_key = re.sub(r'[^\w\-_]', '', key)[:100]
            
            # Sanitize value based on type
            if isinstance(value, str):
                # Remove null bytes and excessive whitespace
                safe_value = value.replace('\x00', '').strip()
                # Truncate very long strings
                if len(safe_value) > 10000:
                    safe_value = safe_value[:10000] + "..."
                sanitized[safe_key] = safe_value
            
            elif isinstance(value, dict):
                sanitized[safe_key] = cls.sanitize_dict(value, max_depth - 1)
            
            elif isinstance(value, list):
                sanitized[safe_key] = [
                    cls.sanitize_dict(item, max_depth - 1) if isinstance(item, dict)
                    else str(item)[:1000] if isinstance(item, str)
                    else item
                    for item in value[:100]  # Limit list size
                ]
            
            elif isinstance(value, (int, float, bool, type(None))):
                sanitized[safe_key] = value
            
            else:
                # Convert other types to string
                sanitized[safe_key] = str(value)[:1000]
        
        return sanitized
    
    @classmethod
    def validate_pagination(cls, skip: int = 0, limit: int = 20) -> tuple:
        """
        Validate pagination parameters
        
        Args:
            skip: Number of items to skip
            limit: Maximum items to return
        
        Returns:
            Validated (skip, limit) tuple
        """
        skip = max(0, skip)
        limit = max(1, min(limit, 100))  # Cap at 100 items per page
        
        return skip, limit


async def validation_middleware(request: Request, call_next):
    """
    Middleware to validate incoming requests
    
    Validates common parameters and sanitizes input data
    """
    try:
        # Skip validation for health checks and metrics
        if request.url.path in ["/health", "/metrics", "/docs", "/openapi.json", "/redoc"]:
            return await call_next(request)
        
        # Validate query parameters
        if request.query_params:
            # Check for excessively long query strings
            query_string = str(request.url.query)
            if len(query_string) > 2048:
                logger.warning(f"Excessively long query string: {len(query_string)} chars")
                return JSONResponse(
                    status_code=400,
                    content={"error": "Query string too long"}
                )
        
        # For POST/PUT requests, validate body size
        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    size = int(content_length)
                    # 10MB limit for request body
                    if size > 10 * 1024 * 1024:
                        logger.warning(f"Request body too large: {size} bytes")
                        return JSONResponse(
                            status_code=413,
                            content={"error": "Request body too large"}
                        )
                except ValueError:
                    pass
        
        # Continue with request
        response = await call_next(request)
        return response
    
    except ValidationError as e:
        logger.warning(f"Validation error: {str(e)}", extra={"path": request.url.path})
        return JSONResponse(
            status_code=400,
            content={"error": str(e)}
        )
    
    except Exception as e:
        logger.error(f"Validation middleware error: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal validation error"}
        )
