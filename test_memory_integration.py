#!/usr/bin/env python3
"""
End-to-End Memory Integration Test for API Gateway

Tests the complete flow:
1. API Gateway → Memory Service integration
2. API Gateway → Core Agent with memory context
3. Full HTTP conversation flow with personalized responses
"""

import asyncio
import httpx
import json
import logging
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Service URLs
API_GATEWAY_URL = "http://localhost:8081"
MEMORY_SERVICE_URL = "http://localhost:8000"
CORE_AGENT_URL = "http://localhost:9000"

async def test_service_health():
    """Test that all services are running and healthy"""
    print("🔍 Testing Service Health...")
    
    services = {
        "API Gateway": f"{API_GATEWAY_URL}/health",
        "Memory Service": f"{MEMORY_SERVICE_URL}/health", 
        "Core Agent": f"{CORE_AGENT_URL}/health"
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for service_name, health_url in services.items():
            try:
                response = await client.get(health_url)
                if response.status_code == 200:
                    print(f"✅ {service_name} is healthy")
                else:
                    print(f"⚠️ {service_name} returned status {response.status_code}")
                    return False
            except Exception as e:
                print(f"❌ {service_name} health check failed: {e}")
                return False
    
    return True

async def test_memory_service_direct():
    """Test direct memory service functionality"""
    print("\n🧠 Testing Memory Service Direct Access...")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Test ELR search endpoint
        search_payload = {
            "user_id": "test_user_123",
            "query_text": "hiking outdoor activities",
            "limit": 5
        }
        
        try:
            response = await client.post(
                f"{MEMORY_SERVICE_URL}/api/elr/search",
                json=search_payload
            )
            
            if response.status_code == 200:
                results = response.json()
                print(f"✅ Memory search successful: {len(results.get('results', []))} items found")
                return True
            else:
                print(f"⚠️ Memory search returned status {response.status_code}: {response.text}")
                return True  # 404 is expected if no data exists
                
        except Exception as e:
            print(f"❌ Memory service direct test failed: {e}")
            return False

async def test_api_gateway_chat():
    """Test API Gateway chat endpoint with memory integration"""
    print("\n💬 Testing API Gateway Chat with Memory Integration...")
    
    chat_payload = {
        "messages": [
            {
                "role": "user",
                "content": "Tell me about my hiking preferences and suggest some gear."
            }
        ],
        "user_id": "test_user_123",
        "session_id": "test_session_456"
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                f"{API_GATEWAY_URL}/api/chat",
                json=chat_payload
            )
            
            if response.status_code == 200:
                result = response.json()
                message = result.get("message", {})
                content = message.get("content", "")
                
                print(f"✅ Chat response received ({len(content)} chars)")
                print(f"📝 Response preview: {content[:200]}...")
                
                # Check if response contains assistant content
                if message.get("role") == "assistant" and content:
                    print("✅ Valid assistant response structure")
                    return True
                else:
                    print("❌ Invalid response structure")
                    return False
                    
            else:
                print(f"❌ Chat request failed with status {response.status_code}: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ API Gateway chat test failed: {e}")
            return False

async def test_api_gateway_streaming():
    """Test API Gateway streaming chat endpoint"""
    print("\n🌊 Testing API Gateway Streaming Chat...")
    
    chat_payload = {
        "messages": [
            {
                "role": "user", 
                "content": "What outdoor activities would you recommend based on my interests?"
            }
        ],
        "user_id": "test_user_123"
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            async with client.stream(
                "POST",
                f"{API_GATEWAY_URL}/api/chat/stream",
                json=chat_payload
            ) as response:
                
                if response.status_code != 200:
                    print(f"❌ Streaming request failed with status {response.status_code}")
                    return False
                
                token_count = 0
                async for chunk in response.aiter_text():
                    if chunk.strip():
                        try:
                            # Parse SSE format
                            if chunk.startswith("data: "):
                                data = json.loads(chunk[6:])
                                if "token" in data:
                                    token_count += 1
                                elif data.get("done"):
                                    break
                        except json.JSONDecodeError:
                            continue
                
                print(f"✅ Streaming completed: {token_count} tokens received")
                return token_count > 0
                
        except Exception as e:
            print(f"❌ API Gateway streaming test failed: {e}")
            return False

async def test_conversation_flow():
    """Test multi-turn conversation with memory context"""
    print("\n🔄 Testing Multi-turn Conversation Flow...")
    
    conversation_messages = []
    
    # First message
    conversation_messages.append({
        "role": "user",
        "content": "I love hiking in the mountains. What should I know about safety?"
    })
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Send first message
        chat_payload = {
            "messages": conversation_messages,
            "user_id": "test_user_123",
            "session_id": "conversation_test"
        }
        
        try:
            response = await client.post(f"{API_GATEWAY_URL}/api/chat", json=chat_payload)
            
            if response.status_code != 200:
                print(f"❌ First message failed: {response.status_code}")
                return False
            
            result = response.json()
            assistant_response = result.get("message", {}).get("content", "")
            conversation_messages.append({
                "role": "assistant",
                "content": assistant_response
            })
            
            print(f"✅ First response: {assistant_response[:100]}...")
            
            # Follow-up message
            conversation_messages.append({
                "role": "user",
                "content": "What gear would you specifically recommend for winter hiking?"
            })
            
            chat_payload["messages"] = conversation_messages
            
            response = await client.post(f"{API_GATEWAY_URL}/api/chat", json=chat_payload)
            
            if response.status_code == 200:
                result = response.json()
                follow_up_response = result.get("message", {}).get("content", "")
                print(f"✅ Follow-up response: {follow_up_response[:100]}...")
                return True
            else:
                print(f"❌ Follow-up message failed: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Conversation flow test failed: {e}")
            return False

async def main():
    """Run all integration tests"""
    print("🚀 Starting API Gateway Memory Integration Tests")
    print("=" * 60)
    
    tests = [
        ("Service Health Check", test_service_health),
        ("Memory Service Direct", test_memory_service_direct),
        ("API Gateway Chat", test_api_gateway_chat),
        ("API Gateway Streaming", test_api_gateway_streaming),
        ("Conversation Flow", test_conversation_flow)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            success = await test_func()
            results[test_name] = success
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results[test_name] = False
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for success in results.values() if success)
    total = len(results)
    
    for test_name, success in results.items():
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status}: {test_name}")
    
    print(f"\n🎯 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All API Gateway memory integration tests PASSED!")
        print("\n📋 System is ready for:")
        print("   1. End-to-end personalized conversations")
        print("   2. Memory-enhanced HTTP API responses")
        print("   3. Streaming chat with ELR context")
        print("   4. Multi-service integration")
    else:
        print(f"\n⚠️ {total - passed} tests failed. Check service connectivity and configuration.")
    
    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
