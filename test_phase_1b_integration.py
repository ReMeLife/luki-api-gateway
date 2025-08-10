#!/usr/bin/env python3
"""
Phase 1B Integration Test Script

This script tests the complete Agent-Gateway integration by:
1. Starting the API gateway server
2. Testing chat endpoints with mock and real agent responses
3. Validating streaming functionality
4. Checking error handling and resilience

Run this after both luki-memory-service and luki-core-agent are running.
"""

import asyncio
import httpx
import json
import time
import logging
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class Phase1BIntegrationTester:
    """Integration tester for Phase 1B Agent-Gateway integration"""
    
    def __init__(self, gateway_url: str = "http://localhost:8080", agent_url: str = "http://localhost:9000"):
        self.gateway_url = gateway_url
        self.agent_url = agent_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    async def test_service_health(self) -> Dict[str, bool]:
        """Test health of all services"""
        results = {}
        
        # Test API Gateway health
        try:
            response = await self.client.get(f"{self.gateway_url}/health")
            results["gateway"] = response.status_code == 200
            logger.info(f"Gateway health: {'✓' if results['gateway'] else '✗'}")
        except Exception as e:
            results["gateway"] = False
            logger.error(f"Gateway health check failed: {e}")
        
        # Test Core Agent health
        try:
            response = await self.client.get(f"{self.agent_url}/health")
            results["agent"] = response.status_code == 200
            logger.info(f"Agent health: {'✓' if results['agent'] else '✗'}")
        except Exception as e:
            results["agent"] = False
            logger.error(f"Agent health check failed: {e}")
        
        return results
    
    async def test_chat_endpoint(self) -> Dict[str, Any]:
        """Test the main chat endpoint"""
        logger.info("Testing chat endpoint...")
        
        test_request = {
            "messages": [
                {"role": "user", "content": "Hello LUKi, tell me about my interests"}
            ],
            "user_id": "test-user-phase1b",
            "session_id": "test-session-phase1b"
        }
        
        try:
            response = await self.client.post(
                f"{self.gateway_url}/v1/chat/",
                json=test_request,
                headers={"Content-Type": "application/json"}
            )
            
            result = {
                "status_code": response.status_code,
                "success": response.status_code == 200,
                "response_time": response.elapsed.total_seconds() if hasattr(response, 'elapsed') else 0
            }
            
            if response.status_code == 200:
                data = response.json()
                result.update({
                    "has_message": "message" in data,
                    "has_session_id": "session_id" in data,
                    "has_metadata": "metadata" in data,
                    "message_role": data.get("message", {}).get("role"),
                    "message_content_length": len(data.get("message", {}).get("content", "")),
                    "response_data": data
                })
                logger.info(f"Chat endpoint: ✓ (response: {result['message_content_length']} chars)")
            else:
                result["error"] = response.text
                logger.error(f"Chat endpoint: ✗ ({response.status_code})")
            
            return result
            
        except Exception as e:
            logger.error(f"Chat endpoint test failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def test_streaming_endpoint(self) -> Dict[str, Any]:
        """Test the streaming chat endpoint"""
        logger.info("Testing streaming endpoint...")
        
        test_request = {
            "messages": [
                {"role": "user", "content": "Tell me a story about hiking"}
            ],
            "user_id": "test-user-stream-phase1b",
            "session_id": "test-session-stream-phase1b"
        }
        
        try:
            async with self.client.stream(
                "POST",
                f"{self.gateway_url}/v1/chat/stream",
                json=test_request,
                headers={"Content-Type": "application/json"}
            ) as response:
                
                result = {
                    "status_code": response.status_code,
                    "success": response.status_code == 200,
                    "is_streaming": response.headers.get("content-type") == "text/event-stream"
                }
                
                if response.status_code == 200:
                    tokens = []
                    chunk_count = 0
                    
                    async for chunk in response.aiter_text():
                        chunk_count += 1
                        if chunk.strip() and chunk.startswith("data: "):
                            try:
                                data = json.loads(chunk[6:].strip())
                                if "token" in data:
                                    tokens.append(data["token"])
                                elif "error" in data:
                                    result["stream_error"] = data["error"]
                                    break
                            except json.JSONDecodeError:
                                pass
                        
                        # Limit test duration
                        if chunk_count > 100:
                            break
                    
                    result.update({
                        "tokens_received": len(tokens),
                        "chunks_processed": chunk_count,
                        "sample_tokens": tokens[:5] if tokens else []
                    })
                    
                    logger.info(f"Streaming endpoint: ✓ ({len(tokens)} tokens, {chunk_count} chunks)")
                else:
                    result["error"] = await response.aread()
                    logger.error(f"Streaming endpoint: ✗ ({response.status_code})")
                
                return result
                
        except Exception as e:
            logger.error(f"Streaming endpoint test failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def test_conversation_flow(self) -> Dict[str, Any]:
        """Test multi-turn conversation flow"""
        logger.info("Testing conversation flow...")
        
        session_id = f"conversation-test-{int(time.time())}"
        user_id = "test-user-conversation"
        
        conversation_turns = [
            "Hello, I'm testing the conversation system",
            "What did I just say to you?",
            "Can you remember our conversation history?"
        ]
        
        results = []
        
        try:
            for i, message in enumerate(conversation_turns):
                # Build conversation history
                messages = []
                for j in range(i):
                    messages.extend([
                        {"role": "user", "content": conversation_turns[j]},
                        {"role": "assistant", "content": f"Response to turn {j+1}"}
                    ])
                messages.append({"role": "user", "content": message})
                
                test_request = {
                    "messages": messages,
                    "user_id": user_id,
                    "session_id": session_id
                }
                
                response = await self.client.post(
                    f"{self.gateway_url}/v1/chat/",
                    json=test_request
                )
                
                turn_result = {
                    "turn": i + 1,
                    "success": response.status_code == 200,
                    "status_code": response.status_code
                }
                
                if response.status_code == 200:
                    data = response.json()
                    turn_result.update({
                        "session_id": data.get("session_id"),
                        "response_length": len(data.get("message", {}).get("content", "")),
                        "has_metadata": "metadata" in data
                    })
                
                results.append(turn_result)
                
                # Small delay between turns
                await asyncio.sleep(0.5)
            
            success_count = sum(1 for r in results if r["success"])
            logger.info(f"Conversation flow: {success_count}/{len(results)} turns successful")
            
            return {
                "success": success_count == len(results),
                "turns": results,
                "success_rate": success_count / len(results)
            }
            
        except Exception as e:
            logger.error(f"Conversation flow test failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def test_error_handling(self) -> Dict[str, Any]:
        """Test error handling scenarios"""
        logger.info("Testing error handling...")
        
        test_cases = [
            {
                "name": "empty_messages",
                "request": {"messages": [], "user_id": "test-user"},
                "expected_status": 400
            },
            {
                "name": "invalid_role",
                "request": {
                    "messages": [{"role": "assistant", "content": "Invalid"}],
                    "user_id": "test-user"
                },
                "expected_status": 400
            },
            {
                "name": "missing_user_id",
                "request": {"messages": [{"role": "user", "content": "Test"}]},
                "expected_status": 422  # Validation error
            }
        ]
        
        results = []
        
        for test_case in test_cases:
            try:
                response = await self.client.post(
                    f"{self.gateway_url}/v1/chat/",
                    json=test_case["request"]
                )
                
                result = {
                    "name": test_case["name"],
                    "success": response.status_code == test_case["expected_status"],
                    "actual_status": response.status_code,
                    "expected_status": test_case["expected_status"]
                }
                
                results.append(result)
                
            except Exception as e:
                results.append({
                    "name": test_case["name"],
                    "success": False,
                    "error": str(e)
                })
        
        success_count = sum(1 for r in results if r["success"])
        logger.info(f"Error handling: {success_count}/{len(results)} cases passed")
        
        return {
            "success": success_count == len(results),
            "cases": results,
            "success_rate": success_count / len(results)
        }
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all integration tests"""
        logger.info("Starting Phase 1B Integration Tests...")
        logger.info("=" * 50)
        
        start_time = time.time()
        
        # Run all tests
        health_results = await self.test_service_health()
        chat_results = await self.test_chat_endpoint()
        streaming_results = await self.test_streaming_endpoint()
        conversation_results = await self.test_conversation_flow()
        error_results = await self.test_error_handling()
        
        end_time = time.time()
        
        # Compile overall results
        overall_results = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration": end_time - start_time,
            "health": health_results,
            "chat_endpoint": chat_results,
            "streaming_endpoint": streaming_results,
            "conversation_flow": conversation_results,
            "error_handling": error_results
        }
        
        # Calculate overall success
        test_successes = [
            health_results.get("gateway", False) and health_results.get("agent", False),
            chat_results.get("success", False),
            streaming_results.get("success", False),
            conversation_results.get("success", False),
            error_results.get("success", False)
        ]
        
        overall_results["overall_success"] = all(test_successes)
        overall_results["success_rate"] = sum(test_successes) / len(test_successes)
        
        # Print summary
        logger.info("=" * 50)
        logger.info("PHASE 1B INTEGRATION TEST RESULTS")
        logger.info("=" * 50)
        logger.info(f"Overall Success: {'✓' if overall_results['overall_success'] else '✗'}")
        logger.info(f"Success Rate: {overall_results['success_rate']:.1%}")
        logger.info(f"Duration: {overall_results['duration']:.2f}s")
        logger.info("")
        logger.info("Individual Tests:")
        logger.info(f"  Health Checks: {'✓' if test_successes[0] else '✗'}")
        logger.info(f"  Chat Endpoint: {'✓' if test_successes[1] else '✗'}")
        logger.info(f"  Streaming: {'✓' if test_successes[2] else '✗'}")
        logger.info(f"  Conversation Flow: {'✓' if test_successes[3] else '✗'}")
        logger.info(f"  Error Handling: {'✓' if test_successes[4] else '✗'}")
        
        return overall_results

async def main():
    """Main test execution"""
    async with Phase1BIntegrationTester() as tester:
        results = await tester.run_all_tests()
        
        # Save results to file
        with open("phase_1b_test_results.json", "w") as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"\nDetailed results saved to: phase_1b_test_results.json")
        
        # Exit with appropriate code
        exit_code = 0 if results["overall_success"] else 1
        return exit_code

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
