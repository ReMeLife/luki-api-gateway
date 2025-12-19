"""
User Uploads API Routes
Provides search and retrieval for user-uploaded files stored in Supabase.
Implements hybrid search: direct keyword matching + semantic expansion for robust file retrieval.
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Set
import logging
from datetime import datetime
import os
import re

from luki_api.clients.memory_service import MemoryServiceClient, ELRQueryRequest
from luki_api.clients.security_service import enforce_policy_scopes

try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
    Client = None

router = APIRouter(prefix="/api/uploads", tags=["uploads"])
logger = logging.getLogger(__name__)

# Initialize Supabase client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase: Optional[Client] = None  # type: ignore

if SUPABASE_URL and SUPABASE_KEY and create_client is not None:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    logger.info("✅ Supabase client initialized for uploads")
else:
    logger.warning("⚠️ Supabase not configured for uploads - file retrieval will fail")


@router.get("/health")
async def uploads_health():
    """Health check for uploads router"""
    return {"status": "ok", "supabase_configured": supabase is not None}


class UploadItem(BaseModel):
    """Upload item metadata"""
    id: str
    object_path: str
    original_filename: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = None
    tags: List[str] = []
    collection_id: Optional[str] = None
    collection_name: Optional[str] = None
    created_at: Optional[str] = None
    signed_url: Optional[str] = None


class UploadSearchResponse(BaseModel):
    """Response for upload search"""
    items: List[UploadItem]
    total: int
    user_id: str
    query: str


class SignedUrlResponse(BaseModel):
    """Response for signed URL request"""
    item_id: str
    signed_url: str
    expires_in: int = 3600


def _normalize_search_terms(query: str) -> List[str]:
    """
    Extract and normalize search terms from a query.
    Handles phrases in quotes, removes common words, and splits into individual terms.
    """
    if not query:
        return []
    
    # Extract quoted phrases first
    quoted = re.findall(r'"([^"]+)"', query)
    remaining = re.sub(r'"[^"]+"', '', query)
    
    # Split remaining into words and filter out common words
    common_words = {'the', 'a', 'an', 'my', 'me', 'i', 'find', 'show', 'get', 'called', 'named', 'titled', 'with', 'of', 'for', 'file', 'image', 'photo', 'picture'}
    words = [w.strip() for w in remaining.lower().split() if w.strip() and w.lower() not in common_words]
    
    # Combine quoted phrases and individual words
    terms = quoted + words
    
    # Remove duplicates while preserving order
    seen: Set[str] = set()
    unique_terms = []
    for term in terms:
        lower_term = term.lower()
        if lower_term not in seen and len(term) >= 2:
            seen.add(lower_term)
            unique_terms.append(term)
    
    return unique_terms


async def _search_supabase_uploads(
    user_id: str, 
    search_terms: List[str], 
    limit: int,
    include_urls: bool
) -> List[UploadItem]:
    """
    Perform robust multi-field search on Supabase elr_upload_items table.
    Uses multiple separate queries to ensure matches are found.
    """
    if not supabase:
        logger.error("❌ [UPLOADS] Supabase client not initialized")
        return []
    
    # Store raw dict rows from Supabase
    raw_items: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()
    
    select_fields = "id, object_path, original_filename, title, description, content_type, size_bytes, tags, collection_id, created_at"
    
    # Strategy 1: If we have search terms, search each field separately
    if search_terms:
        for term in search_terms[:3]:  # Limit to first 3 terms to avoid too many queries
            term_lower = term.lower()
            term_pattern = f"%{term_lower}%"
            
            logger.info(f"🔍 [UPLOADS] Searching for term: '{term}'")
            
            # Search title (most important)
            try:
                title_result = supabase.table("elr_upload_items").select(select_fields).eq(
                    "user_id", user_id
                ).ilike("title", term_pattern).limit(limit).execute()
                
                if title_result.data:
                    logger.info(f"🔍 [UPLOADS] Title search found {len(title_result.data)} items for '{term}'")
                    for row in title_result.data:
                        if row["id"] not in seen_ids:
                            seen_ids.add(row["id"])
                            raw_items.append(row)
            except Exception as e:
                logger.warning(f"⚠️ [UPLOADS] Title search failed: {e}")
            
            # Search original filename
            try:
                filename_result = supabase.table("elr_upload_items").select(select_fields).eq(
                    "user_id", user_id
                ).ilike("original_filename", term_pattern).limit(limit).execute()
                
                if filename_result.data:
                    logger.info(f"🔍 [UPLOADS] Filename search found {len(filename_result.data)} items for '{term}'")
                    for row in filename_result.data:
                        if row["id"] not in seen_ids:
                            seen_ids.add(row["id"])
                            raw_items.append(row)
            except Exception as e:
                logger.warning(f"⚠️ [UPLOADS] Filename search failed: {e}")
            
            # Search description
            try:
                desc_result = supabase.table("elr_upload_items").select(select_fields).eq(
                    "user_id", user_id
                ).ilike("description", term_pattern).limit(limit).execute()
                
                if desc_result.data:
                    logger.info(f"🔍 [UPLOADS] Description search found {len(desc_result.data)} items for '{term}'")
                    for row in desc_result.data:
                        if row["id"] not in seen_ids:
                            seen_ids.add(row["id"])
                            raw_items.append(row)
            except Exception as e:
                logger.warning(f"⚠️ [UPLOADS] Description search failed: {e}")
    
    # If no results from term search, return empty - don't fall back to all files
    # This prevents unrelated queries like "hey" from returning all uploads
    if not raw_items:
        logger.info(f"🔍 [UPLOADS] No matches found for search terms: {search_terms}")
    
    # Convert raw rows to UploadItem objects
    upload_items: List[UploadItem] = []
    
    # Get collection names
    collection_ids = [r.get("collection_id") for r in raw_items if r.get("collection_id")]
    collections_map: Dict[str, str] = {}
    if collection_ids:
        try:
            col_result = supabase.table("elr_upload_collections").select("id, name").in_("id", list(set(collection_ids))).execute()
            if col_result.data:
                collections_map = {c["id"]: c["name"] for c in col_result.data}
        except Exception as e:
            logger.warning(f"⚠️ [UPLOADS] Failed to fetch collection names: {e}")
    
    for row in raw_items[:limit]:
        item = UploadItem(
            id=row["id"],
            object_path=row["object_path"],
            original_filename=row.get("original_filename"),
            title=row.get("title"),
            description=row.get("description"),
            content_type=row.get("content_type"),
            size_bytes=row.get("size_bytes"),
            tags=row.get("tags") or [],
            collection_id=row.get("collection_id"),
            collection_name=collections_map.get(row.get("collection_id", ""), None),
            created_at=row.get("created_at"),
        )
        
        # Generate signed URL if requested
        if include_urls and row.get("object_path"):
            try:
                url_result = supabase.storage.from_("elr-uploads").create_signed_url(
                    row["object_path"], 3600
                )
                if url_result and url_result.get("signedURL"):
                    item.signed_url = url_result["signedURL"]
            except Exception as url_err:
                logger.warning(f"⚠️ [UPLOADS] Failed to generate signed URL: {url_err}")
        
        upload_items.append(item)
    
    return upload_items


@router.get("/{user_id}/search", response_model=UploadSearchResponse)
async def search_uploads(
    user_id: str,
    query: str,
    limit: int = 10,
    include_urls: bool = False
):
    """
    Search user uploads using robust multi-field keyword search.
    
    This searches directly in Supabase across title, filename, and description fields.
    Uses multiple separate queries to ensure reliable matching.
    
    Parameters:
    - user_id: The user ID to search uploads for
    - query: Search query (keywords to match against title, filename, description)
    - limit: Maximum results to return (default: 10)
    - include_urls: If true, generate signed URLs for each result
    
    Returns:
    - Matching uploads sorted by relevance, including all file types (images, PDFs, etc.)
    """
    try:
        query_preview = query[:50] if len(query) > 50 else query
        logger.info(f"🔍 [UPLOADS] Search request: user={user_id}, query='{query_preview}', limit={limit}")
        
        # Policy enforcement
        policy_result = await enforce_policy_scopes(
            user_id=user_id,
            requested_scopes=["elr_memories"],
            requester_role="api_gateway",
            context={"operation": "search_uploads"},
        )
        
        if not policy_result.get("allowed", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient consent to search uploads for this user",
            )
        
        # Extract search terms from query
        search_terms = _normalize_search_terms(query)
        logger.info(f"🔍 [UPLOADS] Extracted search terms: {search_terms}")
        
        # Perform robust multi-field search
        items = await _search_supabase_uploads(user_id, search_terms, limit, include_urls)
        
        logger.info(f"✅ [UPLOADS] Found {len(items)} uploads for user {user_id}")
        
        return UploadSearchResponse(
            items=items,
            total=len(items),
            user_id=user_id,
            query=query
        )
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"❌ [UPLOADS] Search failed: {str(e)}")
        logger.error(f"❌ [UPLOADS] Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search uploads: {str(e)}"
        )


@router.get("/{user_id}/item/{item_id}/url", response_model=SignedUrlResponse)
async def get_upload_url(
    user_id: str,
    item_id: str,
    expires_in: int = 3600
):
    """
    Get a signed URL for a specific upload item.
    
    Parameters:
    - user_id: The user ID (for verification)
    - item_id: The upload item ID
    - expires_in: URL expiration time in seconds (default: 3600)
    
    Returns:
    - Signed URL for the file
    """
    logger.info(f"Getting signed URL for item {item_id} (user: {user_id})")
    
    # Policy enforcement
    policy_result = await enforce_policy_scopes(
        user_id=user_id,
        requested_scopes=["elr_memories"],
        requester_role="api_gateway",
        context={"operation": "get_upload_url"},
    )
    if not policy_result.get("allowed", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient consent to access uploads for this user",
        )
    
    if not supabase:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase storage not configured"
        )
    
    try:
        # Verify user owns this item and get object path
        result = supabase.table("elr_upload_items").select(
            "id, object_path, user_id"
        ).eq("id", item_id).single().execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Upload item not found"
            )
        
        if result.data.get("user_id") != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this item"
            )
        
        object_path = result.data.get("object_path")
        if not object_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File path not found"
            )
        
        # Generate signed URL
        url_result = supabase.storage.from_("elr-uploads").create_signed_url(
            object_path, expires_in
        )
        
        if not url_result or not url_result.get("signedURL"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate signed URL"
            )
        
        return SignedUrlResponse(
            item_id=item_id,
            signed_url=url_result["signedURL"],
            expires_in=expires_in
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get upload URL: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get upload URL: {str(e)}"
        )


@router.get("/{user_id}/recent", response_model=UploadSearchResponse)
async def get_recent_uploads(
    user_id: str,
    limit: int = 10,
    include_urls: bool = False
):
    """
    Get recent uploads for a user.
    
    Parameters:
    - user_id: The user ID
    - limit: Maximum results to return (default: 10)
    - include_urls: If true, generate signed URLs for each result
    
    Returns:
    - Recent uploads sorted by creation date (newest first)
    """
    logger.info(f"Getting recent uploads for user {user_id}")
    
    # Policy enforcement
    policy_result = await enforce_policy_scopes(
        user_id=user_id,
        requested_scopes=["elr_memories"],
        requester_role="api_gateway",
        context={"operation": "get_recent_uploads"},
    )
    if not policy_result.get("allowed", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient consent to access uploads for this user",
        )
    
    if not supabase:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase storage not configured"
        )
    
    try:
        # Query recent uploads directly from Supabase
        result = supabase.table("elr_upload_items").select(
            "id, object_path, original_filename, title, description, content_type, size_bytes, tags, collection_id, created_at"
        ).eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
        
        items: List[UploadItem] = []
        
        if result.data:
            # Get collection names
            collection_ids = [r.get("collection_id") for r in result.data if r.get("collection_id")]
            collections_map: Dict[str, str] = {}
            if collection_ids:
                col_result = supabase.table("elr_upload_collections").select("id, name").in_("id", collection_ids).execute()
                if col_result.data:
                    collections_map = {c["id"]: c["name"] for c in col_result.data}
            
            for row in result.data:
                item = UploadItem(
                    id=row["id"],
                    object_path=row["object_path"],
                    original_filename=row.get("original_filename"),
                    title=row.get("title"),
                    description=row.get("description"),
                    content_type=row.get("content_type"),
                    size_bytes=row.get("size_bytes"),
                    tags=row.get("tags") or [],
                    collection_id=row.get("collection_id"),
                    collection_name=collections_map.get(row.get("collection_id", ""), None),
                    created_at=row.get("created_at"),
                )
                
                # Generate signed URL if requested
                if include_urls and row.get("object_path"):
                    try:
                        url_result = supabase.storage.from_("elr-uploads").create_signed_url(
                            row["object_path"], 3600
                        )
                        if url_result and url_result.get("signedURL"):
                            item.signed_url = url_result["signedURL"]
                    except Exception as url_err:
                        logger.warning(f"Failed to generate signed URL: {url_err}")
                
                items.append(item)
        
        return UploadSearchResponse(
            items=items,
            total=len(items),
            user_id=user_id,
            query=""
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get recent uploads: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get recent uploads: {str(e)}"
        )
