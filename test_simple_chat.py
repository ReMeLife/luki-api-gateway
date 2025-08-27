#!/usr/bin/env python3
"""
Simple API Gateway Chat Test - Minimal test to isolate issues
"""

import asyncio
import httpx
import json

async def test_simple_chat():
    """Test basic chat without memory integration"""
    
    # Simple chat payload
    chat_payload = {
        "messages": [
            {
                "role": "user",
                "content": "Hello, how are you?"
            }
        ],
        "user_id": "test_user",
        "session_id": "test_session"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            print("🔍 Testing simple chat...")
            response = await client.post(
                "http://localhost:8081/api/chat",
                json=chat_payload
            )
            
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
            
            if response.status_code == 200:
                result = response.json()
                print("✅ Chat successful!")
                print(f"Response: {result}")
                return True
            else:
                print(f"❌ Chat failed with status {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ Request failed: {e}")
            return False

if __name__ == "__main__":
    success = asyncio.run(test_simple_chat())
    print(f"Result: {'SUCCESS' if success else 'FAILED'}")
