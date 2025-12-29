"""
Request Validators for LUKi API Gateway

Provides validation utilities for common request patterns including
user IDs, session IDs, pagination, and request bodies.
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional, Any, Dict, Tuple
from uuid import UUID

from ..exceptions import ValidationError, MissingFieldError, InvalidFormatError
from ..constants import Pagination

logger = logging.getLogger(__name__)

# =============================================================================
# REGEX PATTERNS
# =============================================================================

USER_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,256}$")
UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class PaginationParams:
    """Validated pagination parameters"""
    page: int
    page_size: int
    offset: int
    
    @property
    def limit(self) -> int:
        """Alias for page_size"""
        return self.page_size


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def validate_user_id(
    user_id: Any,
    field_name: str = "user_id",
    required: bool = True
) -> Optional[str]:
    """
    Validate user ID format.
    
    Args:
        user_id: User ID to validate
        field_name: Field name for error messages
        required: Whether the field is required
        
    Returns:
        Validated user ID string or None if not required and empty
        
    Raises:
        MissingFieldError: If required and missing
        InvalidFormatError: If format is invalid
    """
    if user_id is None or (isinstance(user_id, str) and not user_id.strip()):
        if required:
            raise MissingFieldError(field_name)
        return None
    
    if not isinstance(user_id, str):
        raise InvalidFormatError(field_name, "string")
    
    user_id = user_id.strip()
    
    if len(user_id) > 128:
        raise ValidationError(
            f"{field_name} exceeds maximum length of 128 characters",
            field=field_name
        )
    
    if not USER_ID_PATTERN.match(user_id):
        raise InvalidFormatError(
            field_name,
            "alphanumeric characters, underscores, and hyphens only"
        )
    
    return user_id


def validate_session_id(
    session_id: Any,
    field_name: str = "session_id",
    required: bool = True
) -> Optional[str]:
    """
    Validate session ID format.
    
    Args:
        session_id: Session ID to validate
        field_name: Field name for error messages
        required: Whether the field is required
        
    Returns:
        Validated session ID string or None if not required and empty
        
    Raises:
        MissingFieldError: If required and missing
        InvalidFormatError: If format is invalid
    """
    if session_id is None or (isinstance(session_id, str) and not session_id.strip()):
        if required:
            raise MissingFieldError(field_name)
        return None
    
    if not isinstance(session_id, str):
        raise InvalidFormatError(field_name, "string")
    
    session_id = session_id.strip()
    
    if len(session_id) > 256:
        raise ValidationError(
            f"{field_name} exceeds maximum length of 256 characters",
            field=field_name
        )
    
    if not SESSION_ID_PATTERN.match(session_id):
        raise InvalidFormatError(field_name, "valid session ID format")
    
    return session_id


def validate_uuid(
    value: Any,
    field_name: str = "id",
    required: bool = True
) -> Optional[str]:
    """
    Validate UUID format.
    
    Args:
        value: UUID string to validate
        field_name: Field name for error messages
        required: Whether the field is required
        
    Returns:
        Validated UUID string or None if not required and empty
        
    Raises:
        MissingFieldError: If required and missing
        InvalidFormatError: If format is invalid
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise MissingFieldError(field_name)
        return None
    
    if not isinstance(value, str):
        raise InvalidFormatError(field_name, "UUID string")
    
    value = value.strip()
    
    # Try to parse as UUID
    try:
        UUID(value)
    except ValueError:
        raise InvalidFormatError(field_name, "valid UUID format (e.g., 123e4567-e89b-12d3-a456-426614174000)")
    
    return value


def validate_pagination(
    page: Any = None,
    page_size: Any = None,
    max_page_size: int = Pagination.MAX_PAGE_SIZE
) -> PaginationParams:
    """
    Validate and normalize pagination parameters.
    
    Args:
        page: Page number (1-indexed)
        page_size: Number of items per page
        max_page_size: Maximum allowed page size
        
    Returns:
        PaginationParams with validated values
        
    Raises:
        ValidationError: If pagination parameters are invalid
    """
    # Default values
    validated_page = Pagination.DEFAULT_PAGE
    validated_page_size = Pagination.DEFAULT_PAGE_SIZE
    
    # Validate page
    if page is not None:
        try:
            validated_page = int(page)
        except (TypeError, ValueError):
            raise ValidationError("page must be an integer", field="page")
        
        if validated_page < 1:
            raise ValidationError("page must be at least 1", field="page")
    
    # Validate page_size
    if page_size is not None:
        try:
            validated_page_size = int(page_size)
        except (TypeError, ValueError):
            raise ValidationError("page_size must be an integer", field="page_size")
        
        if validated_page_size < 1:
            raise ValidationError("page_size must be at least 1", field="page_size")
        
        if validated_page_size > max_page_size:
            raise ValidationError(
                f"page_size cannot exceed {max_page_size}",
                field="page_size"
            )
    
    # Calculate offset
    offset = (validated_page - 1) * validated_page_size
    
    return PaginationParams(
        page=validated_page,
        page_size=validated_page_size,
        offset=offset
    )


def validate_request_body(
    body: Any,
    required_fields: Optional[list] = None,
    optional_fields: Optional[list] = None
) -> Dict[str, Any]:
    """
    Validate request body structure.
    
    Args:
        body: Request body to validate
        required_fields: List of required field names
        optional_fields: List of optional field names (for documentation)
        
    Returns:
        Validated body dictionary
        
    Raises:
        ValidationError: If body structure is invalid
        MissingFieldError: If required field is missing
    """
    if body is None:
        if required_fields:
            raise ValidationError("Request body is required")
        return {}
    
    if not isinstance(body, dict):
        raise ValidationError("Request body must be a JSON object")
    
    # Check required fields
    if required_fields:
        for field in required_fields:
            if field not in body or body[field] is None:
                raise MissingFieldError(field)
    
    return body


def validate_string_field(
    value: Any,
    field_name: str,
    required: bool = True,
    min_length: int = 0,
    max_length: int = 10000,
    allow_empty: bool = False
) -> Optional[str]:
    """
    Validate a string field.
    
    Args:
        value: Value to validate
        field_name: Field name for error messages
        required: Whether the field is required
        min_length: Minimum string length
        max_length: Maximum string length
        allow_empty: Whether empty strings are allowed
        
    Returns:
        Validated string or None
        
    Raises:
        MissingFieldError: If required and missing
        ValidationError: If validation fails
    """
    if value is None:
        if required:
            raise MissingFieldError(field_name)
        return None
    
    if not isinstance(value, str):
        raise InvalidFormatError(field_name, "string")
    
    if not allow_empty and not value.strip():
        if required:
            raise ValidationError(f"{field_name} cannot be empty", field=field_name)
        return None
    
    value = value.strip()
    
    if len(value) < min_length:
        raise ValidationError(
            f"{field_name} must be at least {min_length} characters",
            field=field_name
        )
    
    if len(value) > max_length:
        raise ValidationError(
            f"{field_name} cannot exceed {max_length} characters",
            field=field_name
        )
    
    return value


def validate_integer_field(
    value: Any,
    field_name: str,
    required: bool = True,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None
) -> Optional[int]:
    """
    Validate an integer field.
    
    Args:
        value: Value to validate
        field_name: Field name for error messages
        required: Whether the field is required
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        
    Returns:
        Validated integer or None
        
    Raises:
        MissingFieldError: If required and missing
        ValidationError: If validation fails
    """
    if value is None:
        if required:
            raise MissingFieldError(field_name)
        return None
    
    try:
        int_value = int(value)
    except (TypeError, ValueError):
        raise InvalidFormatError(field_name, "integer")
    
    if min_value is not None and int_value < min_value:
        raise ValidationError(
            f"{field_name} must be at least {min_value}",
            field=field_name
        )
    
    if max_value is not None and int_value > max_value:
        raise ValidationError(
            f"{field_name} cannot exceed {max_value}",
            field=field_name
        )
    
    return int_value
