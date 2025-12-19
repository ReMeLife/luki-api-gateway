
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import httpx
import logging
import json
import re
import asyncio
import time
import uuid
import os
from luki_api.config import settings
from luki_api.clients.agent_client import (
    agent_client,
    AgentChatRequest,
    AgentPhotoReminiscenceImageRequest,
)
from luki_api.clients.memory_service import MemoryServiceClient, ELRQueryRequest
from luki_api.clients.security_service import enforce_policy_scopes
from luki_api.routes.memories import _invalidate_user_memories_cache
from luki_api.middleware.rate_limit import check_daily_message_limit, record_daily_message
from datetime import datetime

router = APIRouter()
logger = logging.getLogger(__name__)
LUKI_ENABLE_AI_MEMORY_DETECTION = os.getenv("LUKI_ENABLE_AI_MEMORY_DETECTION", "false").lower() == "true"

# Import conversation store for auto-saving
try:
    from luki_api.routes.conversations import conversations_store
except ImportError:
    # Fallback if conversations module not loaded yet
    conversations_store = {}


async def save_conversation_to_history(user_id: str, user_message: str, ai_response: str, conversation_id: Optional[str] = None):
    """
    Automatically save conversation messages to history.
    This runs in the background and doesn't block the chat response.
    """
    if (not user_id) or user_id == 'anonymous_base_user' or user_id.startswith('anonymous_'):
        logger.debug(f"Skipping conversation save for anonymous user: {user_id}")
        return None
    
    try:
        # Dynamic import to avoid static analysis errors
        from supabase import create_client  # type: ignore
        import os
        
        SUPABASE_URL = os.getenv("SUPABASE_URL")
        SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        if SUPABASE_URL and SUPABASE_KEY:
            supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            
            # Save to Supabase
            now = datetime.utcnow().isoformat()
            
            # Check if we need to create a new conversation
            if not conversation_id:
                conversation_id = str(uuid.uuid4())
                
                # Create conversation in Supabase
                conv_data = {
                    "id": conversation_id,
                    "user_id": user_id,
                    "title": user_message[:50] + ("..." if len(user_message) > 50 else ""),
                    "preview": user_message[:100],
                    "created_at": now,
                    "updated_at": now
                }
                
                result = supabase.table("conversations").insert(conv_data).execute()
                if result.data:
                    logger.info(f"✅ Created new conversation {conversation_id} for user {user_id} in Supabase")
                else:
                    logger.error(f"Failed to create conversation in Supabase - no data returned")
            
            # Add messages to Supabase
            messages_data = [
                {
                    "conversation_id": conversation_id,
                    "role": "user",
                    "content": user_message,
                    "created_at": now
                },
                {
                    "conversation_id": conversation_id,
                    "role": "assistant", 
                    "content": ai_response,
                    "created_at": datetime.utcnow().isoformat()
                }
            ]
            
            msg_result = supabase.table("messages").insert(messages_data).execute()
            if not msg_result.data:
                logger.error(f"Failed to insert messages to Supabase")
            
            # Update conversation updated_at
            update_result = supabase.table("conversations")\
                .update({"updated_at": datetime.utcnow().isoformat()})\
                .eq("id", conversation_id)\
                .execute()
            if not update_result.data:
                logger.error(f"Failed to update conversation in Supabase")
            
            logger.info(f"✅ Saved conversation {conversation_id} with 2 new messages to Supabase")
            return conversation_id
            
        else:
            # Fallback to in-memory storage if Supabase not configured
            logger.warning("Supabase not configured, using in-memory storage")
            
            # Get or create conversation
            if user_id not in conversations_store:
                conversations_store[user_id] = {}
            
            user_conversations = conversations_store[user_id]
            
            # Create new conversation if needed
            if not conversation_id or conversation_id not in user_conversations:
                conversation_id = str(uuid.uuid4())
                now = datetime.utcnow().isoformat()
                
                user_conversations[conversation_id] = {
                    "id": conversation_id,
                    "user_id": user_id,
                    "title": user_message[:50] + ("..." if len(user_message) > 50 else ""),
                    "preview": user_message[:100],
                    "created_at": now,
                    "updated_at": now,
                    "message_count": 0,
                    "messages": []
                }
                logger.info(f"✅ Created new conversation {conversation_id} for user {user_id}")
            
            conversation = user_conversations[conversation_id]
            
            # Add user message
            conversation["messages"].append({
                "role": "user",
                "content": user_message,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Add AI response
            conversation["messages"].append({
                "role": "assistant",
                "content": ai_response,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Update conversation metadata
            conversation["message_count"] = len(conversation["messages"])
            conversation["updated_at"] = datetime.utcnow().isoformat()
            
            logger.info(f"✅ Saved conversation {conversation_id}: {conversation['message_count']} messages")
            return conversation_id
        
    except Exception as e:
        logger.error(f"❌ Failed to save conversation: {e}")
        # Don't fail the chat request if saving fails
        return None


def extract_memory_content(user_message: str) -> str:
    """Extract distilled memory content from user message.
    Returns only the memory/preference, not the full conversation."""
    
    # Common patterns for memory extraction
    memory_patterns = [
        # Preferences patterns
        (r'i (?:like|love|enjoy|prefer)\s+(.+?)(?:\.|$)', 'I {0} {1}'),
        (r'i (?:hate|dislike)\s+(.+?)(?:\.|$)', 'I {0} {1}'),
        (r'my (?:favorite|favourite)\s+(.+?)\s+(?:is|are)\s+(.+?)(?:\.|$)', 'My favorite {0} is {1}'),
        
        # Identity patterns
        (r'my name is\s+(.+?)(?:\.|$)', 'My name is {0}'),
        (r"i'm\s+(.+?)(?:\.|$)", "I am {0}"),
        (r'i am\s+(.+?)(?:\.|$)', 'I am {0}'),
        (r'call me\s+(.+?)(?:\.|$)', 'Call me {0}'),
        
        # Explicit save patterns
        (r'remember that\s+(.+?)(?:\.|$)', '{0}'),
        (r'save (?:this|that)\s+(.+?)(?:\.|$)', '{0}'),
        (r'please (?:save|remember)\s+(.+?)(?:\.|$)', '{0}'),
    ]
    
    msg_lower = user_message.lower().strip()
    
    # Try to extract using patterns
    import re
    for pattern, template in memory_patterns:
        match = re.search(pattern, msg_lower)
        if match:
            # Get the matched keyword (like/love/hate) and content
            if '{0}' in template and '{1}' in template:
                # Pattern with keyword and content
                keyword = pattern.split('(?:')[1].split(')')[0].split('|')[0]
                if keyword in msg_lower:
                    content = match.group(1)
                else:
                    # Find which keyword was actually used
                    keywords = pattern.split('(?:')[1].split(')')[0].split('|')
                    for kw in keywords:
                        if kw in msg_lower:
                            keyword = kw
                            break
                    content = match.group(1)
                return template.format(keyword, content).capitalize()
            else:
                # Simple pattern with just content
                content = match.group(1) if match.lastindex else match.group(0)
                return template.format(content).capitalize() if '{0}' in template else content.capitalize()
    
    # If no pattern matches but it contains memory keywords, return cleaned version
    if any(kw in msg_lower for kw in ['i like', 'i love', 'i prefer', 'i enjoy', 'i hate', 'i dislike',
                                       'my favorite', 'my favourite', 'remember', 'i am', "i'm"]):
        # Clean up the message
        cleaned = user_message.strip()
        # Remove common prefixes
        prefixes = ['please ', 'can you ', 'could you ', 'would you ', 'save that ', 'remember that ']
        for prefix in prefixes:
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix):]
        return cleaned.capitalize()
    
    # Default: return cleaned message for conversation context
    return user_message.strip()

async def intelligent_memory_detection(user_message: str, conversation_history: Optional[List[Dict[str, str]]] = None) -> Optional[Dict[str, Any]]:
    """
    Use LLM to intelligently detect if message contains memory-worthy content.
    This replaces keyword-based detection with AI-powered understanding.
    
    Returns:
        Dict with 'is_memory', 'content', 'type' if memory detected, else None
    """
    from luki_api.clients.agent_client import agent_client
    
    # Build context from conversation history (last 3 messages for context)
    context_messages = ""
    if conversation_history and len(conversation_history) > 0:
        recent_history = conversation_history[-3:]  # Last 3 exchanges
        context_messages = "\n".join([
            f"{msg['role'].upper()}: {msg['content']}" 
            for msg in recent_history
        ])
    
    # Create a specialized prompt for memory detection
    memory_detection_prompt = f"""You are a memory extraction specialist. Analyze the user's message and determine if it contains information worth saving as a personal memory.

MEMORY-WORTHY CONTENT INCLUDES:
- Personal preferences (likes, dislikes, favorites)
- Personal experiences and stories ("I remember when...", "I once...", "I did...")
- Important life events ("I won a match", "I graduated", "I met someone")
- Personal facts (name, age, occupation, relationships)
- Goals and aspirations ("I want to...", "I hope to...")
- Daily activities they want remembered ("I went to...", "I did... today")
- Feelings about experiences ("it made me happy", "I felt...")
- Requests to save previous context ("save this memory", "remember that")

NOT MEMORY-WORTHY:
- Questions about their memories ("what do you remember about me?")
- General conversation without personal info
- Requests for information or help
- Greetings or small talk

{"CONVERSATION CONTEXT (for reference if user says 'save this' or 'remember that'):" if context_messages else ""}
{context_messages if context_messages else ""}

CURRENT USER MESSAGE:
"{user_message}"

RESPOND IN JSON FORMAT:
{{
  "is_memory": true/false,
  "content": "extracted memory content" or null,
  "type": "preference|experience|fact|goal" or null,
  "reasoning": "brief explanation"
}}

EXAMPLES:

User: "I like burgers"
Response: {{"is_memory": true, "content": "I like burgers", "type": "preference", "reasoning": "Direct preference statement"}}

User: "hey luki, i remember a time when I was young, where I won a football match and it made me so happy"
Response: {{"is_memory": true, "content": "I won a football match when I was young and it made me so happy", "type": "experience", "reasoning": "Personal childhood experience with emotional significance"}}

User: "can you save this memory for me, it makes me happy"
[Previous context shows football story]
Response: {{"is_memory": true, "content": "[extract from previous context]", "type": "experience", "reasoning": "User explicitly requests saving previous story"}}

User: "what do you remember about me?"
Response: {{"is_memory": false, "content": null, "type": null, "reasoning": "Query about memories, not new memory content"}}

Analyze the current message:"""
    
    try:
        # Call the agent with the memory detection prompt
        from luki_api.clients.agent_client import AgentChatRequest
        
        request = AgentChatRequest(
            user_id="system_memory_detector",
            message=memory_detection_prompt,
            session_id=None,
            context={"task": "memory_detection"}
        )
        
        response = await agent_client.chat(request)
        
        # Parse the JSON response
        import json
        import re
        
        # Extract JSON from response (handle markdown code blocks)
        response_text = response.response
        json_match = re.search(r'```json\s*({.*?})\s*```', response_text, re.DOTALL)
        if json_match:
            json_text = json_match.group(1)
        else:
            # Try to find JSON object directly
            json_match = re.search(r'({\s*"is_memory".*?})', response_text, re.DOTALL)
            json_text = json_match.group(1) if json_match else response_text
        
        result = json.loads(json_text)
        logger.info(f"🧠 Memory detection result: {result}")
        
        if result.get('is_memory'):
            return {
                'is_memory': True,
                'content': result.get('content', '').strip(),
                'type': result.get('type', 'preference'),
                'reasoning': result.get('reasoning', '')
            }
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Error in intelligent memory detection: {e}")
        # Fallback to simple keyword detection if AI fails
        return None


async def capture_conversation_elr_safe(user_id: str, user_message: str, ai_response: str, conversation_history: Optional[List[Dict[str, str]]] = None):
    """
    Safe wrapper for capture_conversation_elr that catches exceptions.
    Used for background tasks so they don't crash the main response.
    """
    try:
        await capture_conversation_elr(user_id, user_message, ai_response, conversation_history)
    except Exception as e:
        logger.error(f"❌ Background ELR capture failed for user {user_id}: {e}")
        # Don't raise - background task failure shouldn't affect anything

async def capture_conversation_elr(user_id: str, user_message: str, ai_response: str, conversation_history: Optional[List[Dict[str, str]]] = None):
    """Automatically capture conversation as ELR data - only for authenticated users with AI-powered detection"""
    # Skip ELR capture for anonymous users
    if (not user_id) or user_id == 'anonymous_base_user' or user_id.startswith('anonymous_'):
        logger.debug(f"Skipping ELR capture for anonymous user: {user_id}")
        return
    
    # Skip ELR capture for queries about memories
    msg_lower = user_message.lower()
    is_memory_query = any(phrase in msg_lower for phrase in [
        'list my memories', 'show my memories', 'what do you remember',
        'my saved memories', 'list saved memories', 'show saved memories',
        'what memories', 'retrieve memories', 'get my memories',
        'list all of them', 'show all of them', 'tell me my memories'
    ])
    
    if is_memory_query:
        logger.info(f"Skipping ELR capture for memory query: {user_message[:50]}")
        return
    
    # CRITICAL: Skip if response contains documentation/system content
    # This prevents corrupting memory DB with system documentation
    doc_indicators = [
        'advisory board', 'lustrious partners', 'consultants',
        'LUKi token is intended', 'FINAL NOTES', 'documentation',
        'system prompt', 'API endpoint', 'technical architecture'
    ]
    
    for indicator in doc_indicators:
        if indicator.lower() in ai_response.lower():
            logger.warning(f"Skipping ELR capture - response contains documentation: {indicator}")
            return
    
    policy_result = await enforce_policy_scopes(
        user_id=user_id,
        requested_scopes=["elr_memories"],
        requester_role="api_gateway",
        context={"operation": "capture_conversation_elr"},
    )
    if not policy_result.get("allowed", False):
        logger.info(
            "Skipping ELR capture due to consent policy for user %s",
            user_id,
        )
        return
    
    try:
        memory_client = MemoryServiceClient()

        memory_result: Optional[Dict[str, Any]] = None
        if LUKI_ENABLE_AI_MEMORY_DETECTION:
            memory_result = await intelligent_memory_detection(user_message, conversation_history)

        msg_lower = user_message.lower()
        content: str
        content_type: str

        if memory_result:
            content = (memory_result.get("content") or "").strip()
            if not content:
                return
            raw_type = (memory_result.get("type") or "preference").upper()
            content_type = raw_type

            # Extra guard: if the *user message* is a pure question ("what's my
            # favourite colour?"), do not treat it as a preference memory unless
            # it also contains an explicit preference/save statement.
            if content_type == "PREFERENCE":
                stripped = msg_lower.strip()
                # Very lightweight interrogative detection
                question_starts = (
                    "what", "what's", "whats", "who", "when", "where", "why", "how",
                    "is ", "are ", "do ", "does ", "did ", "can ", "could ", "would ", "will ", "should ", "shall ", "may ", "might ", "am i"
                )
                is_question = "?" in stripped or stripped.startswith(question_starts)
                # Only treat first-person preference verbs or explicit save/remember
                # commands as overrides for questions – not bare phrases like
                # "my favourite" on their own.
                explicit_pref_markers = [
                    "i like ", "i love ", "i enjoy ", "i prefer ",
                    "i hate ", "i dislike ",
                    "remember that ", "save this ", "save that ",
                ]
                has_explicit_pref = any(marker in stripped for marker in explicit_pref_markers)
                if is_question and not has_explicit_pref:
                    logger.info(
                        "Skipping ELR capture for interrogative-only preference question: %s",
                        user_message,
                    )
                    return
        else:
            extracted = extract_memory_content(user_message).strip()
            if not extracted:
                return

            # If extract_memory_content returns the whole message unchanged,
            # apply an extra question filter before relying on loose keywords
            # like "my favourite". This prevents pure questions such as
            # "What's my favourite colour?" from being saved as memories.
            if extracted.lower() == user_message.strip().lower():
                stripped = msg_lower.strip()
                question_starts = (
                    "what", "what's", "whats", "who", "when", "where", "why", "how",
                    "is ", "are ", "do ", "does ", "did ", "can ", "could ", "would ", "will ", "should ", "shall ", "may ", "might ", "am i"
                )
                is_question = "?" in stripped or stripped.startswith(question_starts)

                # Allow question-like forms only when they are explicit memory
                # commands ("remember that ...", "save this ...")
                explicit_memory_commands = (
                    "remember ", "remember that ", "save this ", "save that ", "please save ", "please remember ",
                )
                has_explicit_command = stripped.startswith(explicit_memory_commands)

                keywords = [
                    "i like ",
                    "i love ",
                    "i enjoy ",
                    "i prefer ",
                    "i hate ",
                    "i dislike ",
                    "my favorite",
                    "my favourite",
                    "remember that ",
                    "save this ",
                    "save that ",
                ]

                if is_question and not has_explicit_command:
                    logger.info(
                        "Skipping ELR capture for interrogative-only message with preference keywords: %s",
                        user_message,
                    )
                    return

                if not any(kw in msg_lower for kw in keywords):
                    return

            content = extracted
            if any(kw in msg_lower for kw in ["i like ", "i love ", "i enjoy ", "i prefer ", "i hate ", "i dislike ", "my favorite", "my favourite"]):
                content_type = "PREFERENCE"
            elif any(phrase in msg_lower for phrase in ["i remember", "i once", "i did ", "i went ", "i met ", "i saw "]):
                content_type = "EXPERIENCE"
            elif any(phrase in msg_lower for phrase in ["my name is", "i am ", "i'm ", "i work as", "i live in"]):
                content_type = "FACT"
            else:
                content_type = "FACT"

        logger.info(f"💾 Saving memory: [{content_type}] {content[:100]}...")
        
        elr_data = {
            "user_id": user_id,
            "elr_data": {
                "content": content,  # Now saves distilled content only
                "content_type": content_type,
                "timestamp": datetime.now().isoformat(),
                "metadata": {
                    "source": "chat_widget",
                    "interaction_type": "memory",
                    "authenticated": True,
                    "is_preference": True,
                    "detection_type": "ai_powered",
                    "ai_reasoning": memory_result.get("reasoning", "heuristic") if memory_result else "heuristic",
                    "original_message": user_message[:500],  # Keep original for reference, truncated
                    "ai_response_preview": ai_response[:200]  # Brief AI response preview
                }
            },
            "sensitivity_level": "personal",  # Valid values: public, personal, sensitive, confidential (lowercase)
            "source_file": f"chat_{content_type.lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        }
        
        # Call memory service ingestion endpoint
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{memory_client.base_url.rstrip('/')}/ingestion/elr",
                json=elr_data,
                timeout=5.0,
            )
            if response.status_code == 200:
                logger.info(f"Successfully captured ELR for authenticated user {user_id}")

                # Invalidate cached memory lists so the new memory appears in the
                # MemoryPanel on the next poll instead of waiting for cache TTL.
                try:
                    await _invalidate_user_memories_cache(user_id)
                except Exception as cache_err:
                    # Cache invalidation is best-effort and must never break chat flow
                    logger.warning(
                        "Failed to invalidate memory cache for user %s after ELR capture: %s",
                        user_id,
                        cache_err,
                    )
            else:
                error_detail = response.text if response.text else "No error detail"
                logger.warning(
                    "ELR capture failed with status %s: %s",
                    response.status_code,
                    error_detail,
                )
                
    except Exception as e:
        logger.error(f"ELR capture error: {e}")
        raise

class ChatMessage(BaseModel):
    """Schema for chat messages in the LUKi conversation"""
    role: str = Field(
        description="The role of the message sender",
        examples=["user", "assistant"]
    )
    content: str = Field(
        description="The content of the message"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "role": "user",
                "content": "Tell me about my interests in hiking."
            }
        }


class WalletContext(BaseModel):
    wallet_address: Optional[str] = Field(default=None)
    connected: Optional[bool] = Field(default=None)
    tier: Optional[str] = Field(default=None)
    has_genesis_nft: Optional[bool] = Field(default=None)
    luki_balance: Optional[float] = Field(default=None)


class ChatRequest(BaseModel):
    """Schema for chat requests to the LUKi agent"""
    messages: List[ChatMessage] = Field(
        description="List of chat messages in the conversation history"
    )
    user_id: str = Field(
        description="Unique identifier for the user"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional session identifier for continuing conversations"
    )
    client_tag: Optional[str] = Field(
        default=None,
        description="Optional tag indicating client source (e.g., luki_taster_widget)"
    )
    wallet: Optional[WalletContext] = Field(
        default=None,
        description="Optional wallet/on-chain context for token-gated experiences"
    )
    persona_id: Optional[str] = Field(
        default=None,
        description="Optional persona identifier (e.g. 'default', 'lukicool', 'lukia', or genesis-*) used by the core agent to select LUKi's personality"
    )
    world_day_context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional world day context with name, description, fun_fact, and emoji for today's special day"
    )
    account_tier: Optional[str] = Field(
        default="free",
        description="User's subscription tier (free, plus, pro) - determines daily message limits"
    )
    file_search_mode: Optional[bool] = Field(
        default=False,
        description="When true, triggers explicit file/upload search instead of normal chat"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "messages": [
                    {"role": "user", "content": "Tell me about my interests in hiking."},
                    {"role": "assistant", "content": "Based on your ELR, you enjoy mountain hiking."},
                    {"role": "user", "content": "What gear should I buy?"}
                ],
                "user_id": "user123",
                "session_id": "chat_session_456"
            }
        }

class ChatResponse(BaseModel):
    """Schema for chat responses from the LUKi agent"""
    message: ChatMessage = Field(
        description="The assistant's response message"
    )
    session_id: str = Field(
        description="Session identifier for continuing the conversation"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional metadata about the response such as retrieval sources or confidence"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "message": {
                    "role": "assistant",
                    "content": "Based on your hiking interests, I recommend a good pair of hiking boots, a backpack, and trekking poles for mountain terrain."
                },
                "session_id": "chat_session_456",
                "metadata": {
                    "retrieval_count": 3,
                    "ctx_tokens": 2048,
                    "sources": ["elr_12345", "elr_67890"]
                }
            }
        }


class PhotoReminiscenceImageRequest(BaseModel):
    """Schema for photo reminiscence image generation via gateway"""

    user_id: str = Field(
        description="Unique identifier for the user",
        examples=["user123"],
    )
    activity_title: Optional[str] = Field(
        default=None,
        description="Optional title of the activity (e.g. 'Personal Photo Reminiscence')",
    )
    answers: List[str] = Field(
        description="List of text answers collected during the activity (1-4 items)",
    )
    n: Optional[int] = Field(
        default=1,
        description="Number of images to generate (default 1, max 4)",
    )
    account_tier: Optional[str] = Field(
        default="free",
        description="User's subscription tier (free, plus, pro) - determines image generation limits",
    )

@router.post("/chat", 
         response_model=ChatResponse,
         status_code=status.HTTP_200_OK,
         summary="Chat with LUKi Agent",
         description="Send messages to the LUKi agent and receive personalized responses",
         responses={
             200: {"description": "Successful response from the agent"},
             400: {"description": "Invalid request parameters"},
             401: {"description": "Authentication failed"},
             429: {"description": "Rate limit exceeded"},
             500: {"description": "Agent service error"}
         })
async def chat_endpoint(chat_request: ChatRequest, request: Request):
    """
    Main chat endpoint that communicates with the LUKi core agent
    
    This endpoint processes user messages, retrieves relevant context from the user's 
    Electronic Life Record (ELR), and generates personalized responses using the LUKi agent.
    
    Parameters:
    - **chat_request**: Request object containing messages, user_id, and optional session_id
    
    Returns:
    - **ChatResponse**: Response containing the assistant's message, session ID, and metadata
    
    Raises:
    - **HTTPException 400**: If the request is invalid
    - **HTTPException 401**: If authentication fails
    - **HTTPException 429**: If rate limit is exceeded
    - **HTTPException 500**: If the agent service encounters an error
    """
    logger.info(f"Chat request received for user: {chat_request.user_id}")
    
    try:
        # Validate request
        if not chat_request.messages:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one message is required"
            )
        
        # Get the latest user message
        latest_message = chat_request.messages[-1]
        if latest_message.role != "user":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Latest message must be from user"
            )
        
        # Check daily message limit based on account tier
        account_tier = (chat_request.account_tier or "free").lower()
        rate_limit_error = await check_daily_message_limit(chat_request.user_id, account_tier)
        if rate_limit_error:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=rate_limit_error
            )
        
        # Determine anonymity across all cases
        def is_anonymous(uid: Optional[str], client_tag: Optional[str]) -> bool:
            return (not uid) or uid == 'anonymous_base_user' or uid.startswith('anonymous_') or (client_tag == 'luki_taster_widget')
        # Retrieve memory context from memory service
        memory_context = []
        tasks = []
        memory_client = None
        # User-specific search (only if authenticated)
        if not is_anonymous(chat_request.user_id, chat_request.client_tag):
            try:
                policy_result = await enforce_policy_scopes(
                    user_id=chat_request.user_id,
                    requested_scopes=["elr_memories"],
                    requester_role="api_gateway",
                    context={"operation": "chat_memory_retrieval"},
                )
                if not policy_result.get("allowed", False):
                    logger.info(
                        "Skipping memory retrieval in chat due to consent policy for user %s",
                        chat_request.user_id,
                    )
                else:
                    memory_client = MemoryServiceClient()
                    
                    # Check if user is asking to list memories
                    msg_lower = latest_message.content.lower()
                    is_listing_memories = any(phrase in msg_lower for phrase in [
                        "list my memories", "show my memories", "what do you remember",
                        "my saved memories", "list saved memories", "show saved memories",
                        "what memories", "retrieve memories", "get my memories",
                        "tell me my memories", "all of them", "all my memories",
                        "what are my memories", "show me my memories"
                    ])
                    
                    if is_listing_memories:
                        # Get ALL memories for listing
                        logger.info("User requesting to list all memories")
                        user_query = ELRQueryRequest(
                            user_id=chat_request.user_id,
                            query=" ",  # Use space to get all memories
                            k=50  # Get more memories for listing
                        )
                    else:
                        # Normal semantic search for relevant memories
                        user_query = ELRQueryRequest(
                            user_id=chat_request.user_id,
                            query=latest_message.content,
                            k=5
                        )
                    tasks.append(memory_client.search_elr_items(user_query))
            except Exception as e:
                logger.warning(f"Unable to init user memory query: {e}")
        else:
            logger.debug(f"Skipping user memory retrieval for anonymous user: {chat_request.user_id}")

        # Run queries concurrently and combine results
        if tasks:
            try:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for idx, res in enumerate(results):
                    if isinstance(res, Exception):
                        logger.warning(f"Memory query {idx} failed: {res}")
                        continue
                    if isinstance(res, dict):
                        items = res.get("results", [])
                        memory_context.extend(items)
                    else:
                        logger.warning(f"Memory query {idx} returned non-dict result: {type(res).__name__}")
                logger.info(f"Retrieved total {len(memory_context)} user memory items")
            except Exception as e:
                logger.warning(f"Memory retrieval gather failed: {e}")

        # Prepare agent request with memory and optional wallet context
        agent_context: Dict[str, Any] = {
            "conversation_history": [
                {"role": msg.role, "content": msg.content}
                for msg in chat_request.messages[:-1]  # Exclude the latest message
            ],
            "memory_context": memory_context,
        }
        if chat_request.wallet is not None:
            try:
                agent_context["wallet"] = chat_request.wallet.model_dump()
            except Exception:
                # Defensive: if model_dump is unavailable, fall back to best-effort repr
                agent_context["wallet"] = chat_request.wallet.dict() if hasattr(chat_request.wallet, "dict") else {}

        # Pass persona_id through to core agent so it can select the correct prompt stack
        if chat_request.persona_id:
            agent_context["persona_id"] = chat_request.persona_id

        # Pass world day context for AI awareness of today's special day
        if chat_request.world_day_context:
            agent_context["world_day"] = chat_request.world_day_context

        agent_request = AgentChatRequest(
            message=latest_message.content,
            user_id=chat_request.user_id,
            session_id=chat_request.session_id,
            context=agent_context,
            file_search_mode=chat_request.file_search_mode or False,
        )

        # Call the core agent with timing for debugging
        logger.info(
            "Calling agent service for user %s with session_id=%s",
            chat_request.user_id,
            chat_request.session_id,
        )
        start_agent = time.monotonic()
        agent_response = await agent_client.chat(agent_request)
        agent_elapsed_ms = (time.monotonic() - start_agent) * 1000
        logger.info(
            "Agent service call completed in %.1fms for user %s",
            agent_elapsed_ms,
            chat_request.user_id,
        )
        
        # 🔥 TRUE FIRE-AND-FORGET: Launch memory detection without waiting
        if not is_anonymous(chat_request.user_id, chat_request.client_tag):
            # Pass conversation history for context-aware memory detection
            conversation_history = [
                {"role": msg.role, "content": msg.content} 
                for msg in chat_request.messages
            ]
            
            # Use asyncio.create_task for TRUE background execution (doesn't block connection)
            asyncio.create_task(
                capture_conversation_elr_safe(
                    chat_request.user_id,
                    latest_message.content,
                    agent_response.response,
                    conversation_history
                )
            )
        
        # Defensively extract final text if core returns JSON (e.g., {thought, final_response})
        raw_content = (agent_response.response or "").strip()
        final_text = raw_content
        web_search_used = False
        try:
            data = json.loads(raw_content)
            if isinstance(data, dict) and 'final_response' in data:
                final_text = (data.get('final_response') or "").strip()
                # Capture web_search_used metadata
                web_search_used = data.get('web_search_used', False)
        except Exception:
            m = re.search(r'"final_response"\s*:\s*"(.*?)"', raw_content, flags=re.DOTALL)
            if m:
                final_text = m.group(1).strip()
        # Sanitize any leaked markers
        final_text = re.sub(r'(?im)^(thought|analysis|reflection)\s*:\s*.*$', '', final_text).strip()

        response_message = ChatMessage(
            role="assistant",
            content=final_text
        )
        
        # Include web_search_used in metadata
        response_metadata = agent_response.metadata or {}
        response_metadata['web_search_used'] = web_search_used
        
        # Save conversation to history in background (doesn't block response)
        # Use session_id to track conversation continuity
        # If session_id is None or empty, backend will create a new conversation
        conversation_id = None
        if chat_request.session_id:
            # Validate it's a UUID before using it
            try:
                uuid.UUID(chat_request.session_id)  # Validate it's a UUID
                conversation_id = chat_request.session_id
                logger.info(f"Continuing conversation: {conversation_id}")
            except ValueError:
                logger.info(f"Invalid session_id format: {chat_request.session_id}, creating new conversation")
                conversation_id = None  # Create new conversation
        else:
            logger.info("No session_id provided, creating new conversation")
        
        # Save and get the conversation_id for response
        saved_conversation_id = await save_conversation_to_history(
            user_id=chat_request.user_id,
            user_message=latest_message.content,
            ai_response=final_text,
            conversation_id=conversation_id
        )
        
        # Record the message for daily rate limiting
        await record_daily_message(chat_request.user_id)
        
        # Return the conversation_id as session_id for frontend to use
        # This ensures conversation continuity
        return ChatResponse(
            message=response_message,
            session_id=saved_conversation_id or str(uuid.uuid4()),  # Always return a valid UUID
            metadata=response_metadata
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except httpx.HTTPStatusError as e:
        logger.error(f"Agent service error: {e.response.status_code} - {e.response.text}")
        detail = "Agent service encountered an error."
        try:
            # Try to parse the detail from the agent's response
            error_detail = e.response.json().get("detail")
            if error_detail:
                detail = error_detail
        except Exception:
            pass  # Fallback to generic message
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=detail
        )
    except httpx.RequestError as e:
        logger.error(f"Agent service connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to connect to agent service"
        )
    except Exception as e:
        logger.error(f"Unexpected error in chat endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post(
    "/reme/photo-reminiscence-images",
    status_code=status.HTTP_200_OK,
    summary="Generate images for the Photo Reminiscence activity",
    description=(
        "Generate one or more images based on the user's answers in the "
        "Photo Reminiscence ReMe Made. This proxies to the core agent, which "
        "in turn calls the cognitive module's image service."
    ),
)
async def photo_reminiscence_images_endpoint(
    image_request: PhotoReminiscenceImageRequest,
):
    if not image_request.answers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one answer is required",
        )

    try:
        agent_request = AgentPhotoReminiscenceImageRequest(
            user_id=image_request.user_id,
            activity_title=image_request.activity_title,
            answers=image_request.answers,
            n=image_request.n or 1,
            account_tier=image_request.account_tier or "free",
        )
        result = await agent_client.photo_reminiscence_images(agent_request)
        return result
    except httpx.HTTPStatusError as e:
        # Preserve structured detail from the core agent so the frontend can
        # distinguish rate limits (429) from generic failures.
        try:
            try:
                raw = e.response.json()
            except ValueError:
                raw = {"detail": e.response.text}

            if isinstance(raw, dict):
                container = raw
                inner = container.get("detail", raw)
            else:
                inner = {"message": str(raw)}
        except Exception:
            inner = {"message": "Agent image generation error"}

        logger.error(
            "Agent photo reminiscence images HTTP error: %s - %s",
            e.response.status_code,
            inner,
        )
        raise HTTPException(
            status_code=e.response.status_code,
            detail=inner,
        )
    except httpx.RequestError as e:
        logger.error("Agent photo reminiscence images request error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach agent image generation service",
        )
    except Exception as e:
        logger.error("Unexpected error in photo reminiscence images endpoint: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error during image generation",
        )


@router.post("/chat/stream",
         summary="Streaming Chat with LUKi Agent",
         description="Send messages to the LUKi agent and receive streaming responses for real-time interaction",
         responses={
             200: {"description": "Successful streaming response"},
             400: {"description": "Invalid request parameters"},
             401: {"description": "Authentication failed"},
             429: {"description": "Rate limit exceeded"},
             500: {"description": "Agent service error"}
         })
async def chat_stream_endpoint(chat_request: ChatRequest, request: Request):
    """
    Streaming chat endpoint for real-time responses
    
    This endpoint provides a server-sent events (SSE) stream of tokens from the LUKi agent
    for real-time, token-by-token response rendering in the client interface.
    
    Parameters:
    - **chat_request**: Request object containing messages, user_id, and optional session_id
    
    Returns:
    - **StreamingResponse**: Server-sent events stream of response tokens
    
    Raises:
    - **HTTPException 400**: If the request is invalid
    - **HTTPException 401**: If authentication fails
    - **HTTPException 429**: If rate limit is exceeded
    - **HTTPException 500**: If the agent service encounters an error
    """
    logger.info(f"Streaming chat request received for user: {chat_request.user_id}")
    
    async def generate_stream():
        try:
            # Validate request
            if not chat_request.messages:
                yield f"data: {json.dumps({'error': 'At least one message is required'})}\n\n"
                return
            
            # Get the latest user message
            latest_message = chat_request.messages[-1]
            if latest_message.role != "user":
                yield f"data: {json.dumps({'error': 'Latest message must be from user'})}\n\n"
                return
            
            # Retrieve memory context from memory service for streaming - only if authenticated
            def is_anonymous(uid: Optional[str], client_tag: Optional[str]) -> bool:
                return (not uid) or uid == 'anonymous_base_user' or uid.startswith('anonymous_') or (client_tag == 'luki_taster_widget')

            memory_context = []
            tasks = []
            memory_client = None
            if not is_anonymous(chat_request.user_id, chat_request.client_tag):
                try:
                    policy_result = await enforce_policy_scopes(
                        user_id=chat_request.user_id,
                        requested_scopes=["elr_memories"],
                        requester_role="api_gateway",
                        context={"operation": "chat_stream_memory_retrieval"},
                    )
                    if not policy_result.get("allowed", False):
                        logger.info(
                            "Skipping memory retrieval in streaming chat due to consent policy for user %s",
                            chat_request.user_id,
                        )
                    else:
                        memory_client = MemoryServiceClient()
                        user_query = ELRQueryRequest(
                            user_id=chat_request.user_id,
                            query=latest_message.content,
                            k=5
                        )
                        tasks.append(memory_client.search_elr_items(user_query))
                except Exception as e:
                    logger.warning(f"Unable to init user memory query (stream): {e}")
            else:
                logger.debug(f"Skipping user memory retrieval for anonymous streaming user: {chat_request.user_id}")


            if tasks:
                try:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for idx, res in enumerate(results):
                        if isinstance(res, Exception):
                            logger.warning(f"Memory query (stream) {idx} failed: {res}")
                            continue
                        if isinstance(res, dict):
                            items = res.get("results", [])
                            memory_context.extend([item for item in items if isinstance(item, dict)])
                        else:
                            logger.warning(f"Memory query (stream) {idx} returned non-dict result: {type(res).__name__}")
                    logger.info(f"Retrieved total {len(memory_context)} user memory items for streaming")
                except Exception as e:
                    logger.warning(f"Memory retrieval gather (stream) failed: {e}")
            # Prepare agent request with memory and optional wallet context
            agent_context: Dict[str, Any] = {
                "conversation_history": [
                    {"role": msg.role, "content": msg.content}
                    for msg in chat_request.messages[:-1]
                ],
                "memory_context": memory_context,
            }
            if chat_request.wallet is not None:
                try:
                    agent_context["wallet"] = chat_request.wallet.model_dump()
                except Exception:
                    agent_context["wallet"] = chat_request.wallet.dict() if hasattr(chat_request.wallet, "dict") else {}

            if chat_request.persona_id:
                agent_context["persona_id"] = chat_request.persona_id

            # Pass world day context for AI awareness of today's special day
            if chat_request.world_day_context:
                agent_context["world_day"] = chat_request.world_day_context

            agent_request = AgentChatRequest(
                message=latest_message.content,
                user_id=chat_request.user_id,
                session_id=chat_request.session_id,
                context=agent_context,
                file_search_mode=chat_request.file_search_mode or False,
            )
            
            # Stream response directly from agent; sanitization is handled by the core agent.
            async for token in agent_client.chat_stream(agent_request):
                if token:
                    yield f"data: {json.dumps({'token': token})}\n\n"
            
            # Send completion signal
            yield f"data: {json.dumps({'done': True})}\n\n"
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Agent service streaming error: {e.response.status_code}")
            yield f"data: {json.dumps({'error': 'Agent service unavailable'})}\n\n"
        except httpx.RequestError as e:
            logger.error(f"Agent service streaming connection error: {e}")
            yield f"data: {json.dumps({'error': 'Unable to connect to agent service'})}\n\n"
        except Exception as e:
            logger.error(f"Unexpected error in streaming endpoint: {e}")
            yield f"data: {json.dumps({'error': 'Internal server error'})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )
