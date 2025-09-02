#!/usr/bin/env python3
"""
Integration test script for LUKi API Gateway with Together AI backend
"""

import asyncio
import httpx
import json
import sys
from pathlib import Path

# Add the luki_api package to Python path
sys.path.insert(0, str(Path(__file__).parent))

async def test_api_gateway_integration():
    """Test API Gateway integration with core agent"""
    print("🧪 Testing LUKi API Gateway Integration")
    print("=" * 60)
    
    base_url = "http://localhost:8081"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Test 1: Health check
            print("\n1. Testing health endpoint...")
            response = await client.get(f"{base_url}/health")
            if response.status_code == 200:
                print("✅ Health check passed")
                health_data = response.json()
                print(f"   Status: {health_data.get('status')}")
                print(f"   Agent service: {health_data.get('services', {}).get('agent', 'unknown')}")
            else:
                print(f"❌ Health check failed: {response.status_code}")
                return False
            
            # Test 2: Chat endpoint
            print("\n2. Testing chat endpoint...")
            chat_payload = {
                "messages": [
                    {"role": "user", "content": "Hello! Please introduce yourself as LUKi."}
                ],
                "user_id": "test_user_123",
                "session_id": "test_session_456"
            }
            
            response = await client.post(
                f"{base_url}/v1/chat",
                json=chat_payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                print("✅ Chat endpoint working")
                chat_data = response.json()
                print(f"   Response: {chat_data.get('message', {}).get('content', '')[:100]}...")
                print(f"   Session ID: {chat_data.get('session_id')}")
            else:
                print(f"❌ Chat endpoint failed: {response.status_code}")
                print(f"   Error: {response.text}")
                return False
            
            # Test 3: Streaming chat endpoint
            print("\n3. Testing streaming chat endpoint...")
            stream_payload = {
                "messages": [
                    {"role": "user", "content": "Tell me a short story about AI companionship."}
                ],
                "user_id": "test_user_123",
                "session_id": "test_session_789"
            }
            
            async with client.stream(
                "POST",
                f"{base_url}/v1/chat/stream",
                json=stream_payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status_code == 200:
                    print("✅ Streaming endpoint working")
                    print("   Stream content:")
                    
                    token_count = 0
                    async for chunk in response.aiter_text():
                        if chunk.strip():
                            if chunk.startswith("data: "):
                                data_str = chunk[6:].strip()
                                if data_str and data_str != "[DONE]":
                                    try:
                                        data = json.loads(data_str)
                                        if "token" in data:
                                            print(data["token"], end="", flush=True)
                                            token_count += 1
                                        elif "done" in data and data["done"]:
                                            break
                                    except json.JSONDecodeError:
                                        continue
                    
                    print(f"\n   Received {token_count} tokens")
                else:
                    print(f"❌ Streaming endpoint failed: {response.status_code}")
                    return False
            
            print("\n🎉 All API Gateway tests passed!")
            return True
            
        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
            return False

async def main():
    """Run API Gateway integration tests"""
    print("🚀 Starting API Gateway Integration Tests")
    
    success = await test_api_gateway_integration()
    
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    if success:
        print("✅ API Gateway integration tests PASSED!")
        print("\n📋 Next steps:")
        print("   1. Start the core agent service on port 9000")
        print("   2. Start the API gateway on port 8081")
        print("   3. Test end-to-end conversation flow")
        print("   4. Integrate with memory service for context retrieval")
    else:
        print("❌ API Gateway integration tests FAILED!")
        print("\n🔧 Troubleshooting:")
        print("   1. Ensure core agent is running on port 9000")
        print("   2. Check API gateway configuration")
        print("   3. Verify network connectivity between services")
    
    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
