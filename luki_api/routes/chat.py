
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import httpx
import logging
import json
import re
import asyncio
import uuid
from luki_api.config import settings
from luki_api.clients.agent_client import agent_client, AgentChatRequest
from luki_api.clients.memory_service import MemoryServiceClient, ELRQueryRequest
from datetime import datetime

router = APIRouter()
logger = logging.getLogger(__name__)

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
    
    try:
        memory_client = MemoryServiceClient()
        
        # 🔥 NEW: Use AI-powered memory detection instead of keywords
        memory_result = await intelligent_memory_detection(user_message, conversation_history)
        
        # Skip saving if AI determined it's not a memory
        if not memory_result:
            logger.debug(f"AI determined not a memory: {user_message[:50]}")
            return
        
        # Extract distilled memory content using AI result
        content = memory_result['content']
        content_type = memory_result['type'].upper()  # PREFERENCE, EXPERIENCE, FACT, GOAL
        
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
                    "ai_reasoning": memory_result['reasoning'],
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
                timeout=5.0
            )
            if response.status_code == 200:
                logger.info(f"Successfully captured ELR for authenticated user {user_id}")
            else:
                error_detail = response.text if response.text else "No error detail"
                logger.warning(f"ELR capture failed with status {response.status_code}: {error_detail}")
                
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

        # Prepare agent request with memory context
        agent_request = AgentChatRequest(
            message=latest_message.content,
            user_id=chat_request.user_id,
            session_id=chat_request.session_id,
            context={
                "conversation_history": [
                    {"role": msg.role, "content": msg.content} 
                    for msg in chat_request.messages[:-1]  # Exclude the latest message
                ],
                "memory_context": memory_context
            }
        )
        
        # Call the core agent
        agent_response = await agent_client.chat(agent_request)
        
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
            # Prepare agent request with memory context
            agent_request = AgentChatRequest(
                message=latest_message.content,
                user_id=chat_request.user_id,
                session_id=chat_request.session_id,
                context={
                    "conversation_history": [
                        {"role": msg.role, "content": msg.content} 
                        for msg in chat_request.messages[:-1]
                    ],
                    "memory_context": memory_context
                }
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
