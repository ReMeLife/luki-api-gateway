"""
Error response models for the API Gateway.

This module defines standardized error response models for use across API endpoints.
These models provide consistent error formatting and detailed OpenAPI documentation.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class ErrorDetail(BaseModel):
    """Model for detailed error information"""
    code: str = Field(
        ..., 
        description="Error code identifier",
        examples=["INVALID_INPUT", "AUTHORIZATION_ERROR", "RESOURCE_NOT_FOUND"]
    )
    message: str = Field(
        ..., 
        description="Human-readable error message",
        examples=["Invalid input data", "User not authorized", "Resource not found"]
    )
    param: Optional[str] = Field(
        None, 
        description="Parameter that caused the error, if applicable",
        examples=["user_id", "item_id", "query_text"]
    )
    location: Optional[str] = Field(
        None, 
        description="Location of the error (path, query, header, body)",
        examples=["path", "query", "header", "body"]
    )


class ErrorResponse(BaseModel):
    """Standard error response model for API errors"""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "status": "error",
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Validation error on input data",
                        "param": "user_id",
                        "location": "path"
                    },
                    "details": [
                        {
                            "code": "INVALID_FORMAT",
                            "message": "Invalid format for user_id",
                            "param": "user_id",
                            "location": "path"
                        }
                    ]
                }
            ]
        }
    )
    
    status: str = Field(
        "error", 
        description="Response status indicator",
        examples=["error"]
    )
    error: ErrorDetail = Field(
        ...,
        description="Main error information"
    )
    details: Optional[List[ErrorDetail]] = Field(
        None,
        description="Additional error details for multiple errors"
    )


# Predefined common error responses
UNAUTHORIZED_RESPONSE = {
    "model": ErrorResponse,
    "description": "Authentication error",
    "content": {
        "application/json": {
            "examples": {
                "missing_auth": {
                    "summary": "Missing authentication",
                    "value": {
                        "status": "error",
                        "error": {
                            "code": "AUTHENTICATION_REQUIRED",
                            "message": "Authentication required. Provide API key or JWT token."
                        }
                    }
                },
                "invalid_api_key": {
                    "summary": "Invalid API key",
                    "value": {
                        "status": "error",
                        "error": {
                            "code": "INVALID_API_KEY",
                            "message": "Invalid API key provided",
                            "param": "X-API-Key",
                            "location": "header"
                        }
                    }
                },
                "invalid_jwt": {
                    "summary": "Invalid JWT token",
                    "value": {
                        "status": "error",
                        "error": {
                            "code": "INVALID_JWT_TOKEN",
                            "message": "Invalid or expired JWT token",
                            "param": "Authorization",
                            "location": "header"
                        }
                    }
                }
            }
        }
    }
}

FORBIDDEN_RESPONSE = {
    "model": ErrorResponse,
    "description": "Authorization error",
    "content": {
        "application/json": {
            "examples": {
                "insufficient_permissions": {
                    "summary": "Insufficient permissions",
                    "value": {
                        "status": "error",
                        "error": {
                            "code": "INSUFFICIENT_PERMISSIONS",
                            "message": "Insufficient permissions to access this resource"
                        }
                    }
                }
            }
        }
    }
}

NOT_FOUND_RESPONSE = {
    "model": ErrorResponse,
    "description": "Resource not found",
    "content": {
        "application/json": {
            "examples": {
                "item_not_found": {
                    "summary": "Item not found",
                    "value": {
                        "status": "error",
                        "error": {
                            "code": "RESOURCE_NOT_FOUND",
                            "message": "The requested resource was not found",
                            "param": "item_id",
                            "location": "path"
                        }
                    }
                }
            }
        }
    }
}

VALIDATION_ERROR_RESPONSE = {
    "model": ErrorResponse,
    "description": "Validation error",
    "content": {
        "application/json": {
            "examples": {
                "invalid_input": {
                    "summary": "Invalid input data",
                    "value": {
                        "status": "error",
                        "error": {
                            "code": "VALIDATION_ERROR",
                            "message": "Invalid input data"
                        },
                        "details": [
                            {
                                "code": "INVALID_FORMAT",
                                "message": "Invalid format for user_id",
                                "param": "user_id",
                                "location": "body"
                            }
                        ]
                    }
                }
            }
        }
    }
}

RATE_LIMIT_RESPONSE = {
    "model": ErrorResponse,
    "description": "Rate limit exceeded",
    "content": {
        "application/json": {
            "examples": {
                "rate_limit": {
                    "summary": "Rate limit exceeded",
                    "value": {
                        "status": "error",
                        "error": {
                            "code": "RATE_LIMIT_EXCEEDED",
                            "message": "Rate limit exceeded. Try again in 60 seconds."
                        }
                    }
                }
            }
        }
    }
}

SERVER_ERROR_RESPONSE = {
    "model": ErrorResponse,
    "description": "Internal server error",
    "content": {
        "application/json": {
            "examples": {
                "server_error": {
                    "summary": "Internal server error",
                    "value": {
                        "status": "error",
                        "error": {
                            "code": "INTERNAL_SERVER_ERROR",
                            "message": "An unexpected error occurred"
                        }
                    }
                }
            }
        }
    }
}

# Dictionary of common responses for easy reference in route definitions
COMMON_RESPONSES = {
    401: UNAUTHORIZED_RESPONSE,
    403: FORBIDDEN_RESPONSE,
    404: NOT_FOUND_RESPONSE,
    422: VALIDATION_ERROR_RESPONSE,
    429: RATE_LIMIT_RESPONSE,
    500: SERVER_ERROR_RESPONSE
}
