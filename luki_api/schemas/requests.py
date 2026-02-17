"""
Request validation schemas for LUKi API Gateway
Comprehensive Pydantic models for all API endpoints
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime
from enum import Enum


class UserTier(str, Enum):
    """User subscription tiers"""
    FREE = "free"
    PLUS = "plus"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class ConsentScope(str, Enum):
    """Consent scope types"""
    ELR_READ = "elr_read"
    ELR_WRITE = "elr_write"
    ANALYTICS = "analytics"
    PERSONALIZATION = "personalization"
    RESEARCH = "research"


# ============================================================================
# Chat Request Schemas
# ============================================================================

class ChatRequest(BaseModel):
    """Base chat request"""
    user_id: str = Field(..., min_length=3, max_length=128, description="User identifier")
    message: str = Field(..., min_length=1, max_length=10000, description="User message")
    conversation_id: Optional[str] = Field(None, max_length=128, description="Conversation ID for continuity")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context")
    stream: bool = Field(False, description="Whether to stream response")
    
    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Validate message content"""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Message cannot be empty or whitespace only")
        return stripped
    
    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        """Validate user_id format"""
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("user_id must be alphanumeric with optional _ or -")
        return v


class ChatStreamRequest(BaseModel):
    """Streaming chat request"""
    user_id: str = Field(..., min_length=3, max_length=128)
    message: str = Field(..., min_length=1, max_length=10000)
    conversation_id: Optional[str] = Field(None, max_length=128)
    
    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        return v.strip()


# ============================================================================
# Memory/ELR Request Schemas
# ============================================================================

class ELRIngestTextRequest(BaseModel):
    """Request to ingest text into ELR"""
    user_id: str = Field(..., min_length=3, max_length=128)
    text: str = Field(..., min_length=1, max_length=100000, description="Text content to ingest")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata")
    source: Optional[str] = Field(None, max_length=256, description="Source of the text")
    timestamp: Optional[datetime] = Field(None, description="Timestamp of content")
    
    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Text cannot be empty")
        return stripped


class ELRQueryRequest(BaseModel):
    """Request to query ELR memories"""
    user_id: str = Field(..., min_length=3, max_length=128)
    query: str = Field(..., min_length=1, max_length=500, description="Search query")
    top_k: int = Field(5, ge=1, le=50, description="Number of results to return")
    filters: Optional[Dict[str, Any]] = Field(None, description="Optional filters")
    
    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        return v.strip()


class MemoryDeleteRequest(BaseModel):
    """Request to delete specific memories"""
    user_id: str = Field(..., min_length=3, max_length=128)
    memory_ids: List[str] = Field(..., min_items=1, max_items=100, description="Memory IDs to delete")
    
    @field_validator("memory_ids")
    @classmethod
    def validate_memory_ids(cls, v: List[str]) -> List[str]:
        """Ensure no duplicate IDs"""
        if len(v) != len(set(v)):
            raise ValueError("Duplicate memory IDs not allowed")
        return v


# ============================================================================
# Activity Request Schemas
# ============================================================================

class ActivityRecommendRequest(BaseModel):
    """Request activity recommendations"""
    user_id: str = Field(..., min_length=3, max_length=128)
    interests: Optional[List[str]] = Field(None, max_items=20, description="User interests")
    difficulty_level: Optional[float] = Field(None, ge=0.0, le=1.0, description="Difficulty (0-1)")
    top_k: int = Field(3, ge=1, le=20, description="Number of recommendations")
    
    @field_validator("interests")
    @classmethod
    def validate_interests(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v:
            # Remove empty strings and duplicates
            cleaned = list(set(i.strip() for i in v if i.strip()))
            return cleaned if cleaned else None
        return v


class ActivityFeedbackRequest(BaseModel):
    """Submit activity feedback"""
    user_id: str = Field(..., min_length=3, max_length=128)
    activity_id: str = Field(..., min_length=1, max_length=128)
    rating: float = Field(..., ge=0.0, le=1.0, description="Rating (0-1)")
    completion_time_seconds: Optional[float] = Field(None, ge=0, description="Time to complete")
    feedback_text: Optional[str] = Field(None, max_length=5000, description="Optional feedback")


# ============================================================================
# Report Request Schemas
# ============================================================================

class WellbeingReportRequest(BaseModel):
    """Request wellbeing report generation"""
    user_id: str = Field(..., min_length=3, max_length=128)
    window_days: int = Field(7, ge=1, le=90, description="Days to include in report")
    include_charts: bool = Field(False, description="Include chart data")
    recipient_type: str = Field("user", pattern="^(user|family|clinician)$")
    
    @field_validator("recipient_type")
    @classmethod
    def validate_recipient(cls, v: str) -> str:
        valid_types = ["user", "family", "clinician"]
        if v not in valid_types:
            raise ValueError(f"recipient_type must be one of: {', '.join(valid_types)}")
        return v


class AnalyticsSummaryRequest(BaseModel):
    """Request analytics summary"""
    user_id: str = Field(..., min_length=3, max_length=128)
    start_date: Optional[datetime] = Field(None, description="Start date for analytics")
    end_date: Optional[datetime] = Field(None, description="End date for analytics")
    metrics: Optional[List[str]] = Field(None, max_items=20, description="Specific metrics to include")
    
    @model_validator(mode='after')
    def validate_date_range(self):
        """Validate date range if provided"""
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                raise ValueError("start_date must be before end_date")
        return self


# ============================================================================
# Image Generation Request Schemas
# ============================================================================

class ImageGenerationRequest(BaseModel):
    """Request image generation"""
    user_id: str = Field(..., min_length=3, max_length=128)
    prompt: str = Field(..., min_length=10, max_length=1000, description="Image generation prompt")
    style: Optional[str] = Field(None, max_length=100, description="Image style")
    quality: str = Field("standard", pattern="^(standard|high)$")
    
    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        stripped = v.strip()
        if len(stripped) < 10:
            raise ValueError("Prompt must be at least 10 characters")
        return stripped


# ============================================================================
# Consent & Privacy Request Schemas
# ============================================================================

class ConsentUpdateRequest(BaseModel):
    """Update user consent preferences"""
    user_id: str = Field(..., min_length=3, max_length=128)
    scopes: Dict[ConsentScope, bool] = Field(..., description="Consent scopes and values")
    ip_address: Optional[str] = Field(None, max_length=45, description="IP address for audit")
    
    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, v: Dict[ConsentScope, bool]) -> Dict[ConsentScope, bool]:
        if not v:
            raise ValueError("At least one consent scope must be specified")
        return v


class PrivacySettingsRequest(BaseModel):
    """Update privacy settings"""
    user_id: str = Field(..., min_length=3, max_length=128)
    analytics_enabled: Optional[bool] = None
    personalization_enabled: Optional[bool] = None
    data_retention_days: Optional[int] = Field(None, ge=30, le=3650, description="Data retention period")


# ============================================================================
# Wallet & NFT Request Schemas
# ============================================================================

class WalletVerifyRequest(BaseModel):
    """Verify wallet ownership"""
    wallet_address: str = Field(..., min_length=32, max_length=64, description="Solana wallet address")
    signature: str = Field(..., min_length=64, description="Signed message")
    nonce: str = Field(..., min_length=16, max_length=64, description="Nonce from server")
    
    @field_validator("wallet_address")
    @classmethod
    def validate_wallet_address(cls, v: str) -> str:
        # Basic Solana address validation (base58, typically 32-44 chars)
        if not v.isalnum():
            raise ValueError("Invalid wallet address format")
        return v


class WalletEntitlementsRequest(BaseModel):
    """Request wallet entitlements"""
    wallet_address: str = Field(..., min_length=32, max_length=64)


# ============================================================================
# Conversation Management Schemas
# ============================================================================

class ConversationCreateRequest(BaseModel):
    """Create new conversation"""
    user_id: str = Field(..., min_length=3, max_length=128)
    title: Optional[str] = Field(None, max_length=200, description="Conversation title")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata")


class ConversationUpdateRequest(BaseModel):
    """Update existing conversation"""
    conversation_id: str = Field(..., min_length=1, max_length=128)
    title: Optional[str] = Field(None, max_length=200)
    archived: Optional[bool] = None


class ConversationListRequest(BaseModel):
    """List conversations"""
    user_id: str = Field(..., min_length=3, max_length=128)
    limit: int = Field(20, ge=1, le=100, description="Number of conversations to return")
    offset: int = Field(0, ge=0, description="Pagination offset")
    include_archived: bool = Field(False, description="Include archived conversations")


# ============================================================================
# Upload Request Schemas
# ============================================================================

class UploadMetadata(BaseModel):
    """Metadata for file upload"""
    user_id: str = Field(..., min_length=3, max_length=128)
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., max_length=100)
    file_size_bytes: int = Field(..., ge=1, le=100_000_000, description="File size in bytes")
    description: Optional[str] = Field(None, max_length=1000)
    
    @field_validator("content_type")
    @classmethod
    def validate_content_type(cls, v: str) -> str:
        allowed_types = [
            "image/jpeg", "image/png", "image/gif", "image/webp",
            "application/pdf", "text/plain", "text/csv",
            "audio/mpeg", "audio/wav", "video/mp4"
        ]
        if v not in allowed_types:
            raise ValueError(f"Content type {v} not allowed")
        return v


# ============================================================================
# Health & Status Schemas
# ============================================================================

class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: str = Field(..., pattern="^(healthy|degraded|unhealthy)$")
    timestamp: datetime
    version: Optional[str] = None
    components: Optional[Dict[str, str]] = None


class MetricsRequest(BaseModel):
    """Request for metrics data"""
    format: str = Field("json", pattern="^(json|prometheus)$")
    include_histograms: bool = Field(True, description="Include histogram data")
