"""
Integration tests for Agent-Gateway communication

Tests the complete integration between the API gateway and the LUKi core agent,
including chat endpoints, streaming, error handling, and end-to-end flows.
"""

import pytest
import httpx
import json
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from luki_api.main import app
from luki_api.clients.agent_client import AgentClient, AgentChatRequest, AgentChatResponse

class TestAgentIntegration:
    """Test suite for agent-gateway integration"""
    
    @pytest.fixture
    def client(self):
        """Test client fixture"""
        return TestClient(app)
    
    @pytest.fixture
    def mock_agent_response(self):
        """Mock agent response fixture"""
        return AgentChatResponse(
            response="Hello! I'm LUKi, your AI companion. How can I help you today?",
            session_id="test-session-123",
            metadata={
                "retrieval_count": 3,
                "ctx_tokens": 1250,
                "tool_calls": 0
            }
        )
    
    @pytest.fixture
    def sample_chat_request(self):
        """Sample chat request fixture"""
        return {
            "messages": [
                {"role": "user", "content": "Hello, tell me about my hiking interests"}
            ],
            "user_id": "test-user-123",
            "session_id": "test-session-123"
        }
    
    def test_chat_endpoint_success(self, client, sample_chat_request, mock_agent_response):
        """Test successful chat endpoint integration"""
        with patch('luki_api.clients.agent_client.agent_client.chat') as mock_chat:
            mock_chat.return_value = mock_agent_response
            
            response = client.post("/v1/chat/", json=sample_chat_request)
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify response structure
            assert "message" in data
            assert "session_id" in data
            assert "metadata" in data
            
            # Verify message content
            assert data["message"]["role"] == "assistant"
            assert data["message"]["content"] == mock_agent_response.response
            assert data["session_id"] == mock_agent_response.session_id
            assert data["metadata"] == mock_agent_response.metadata
            
            # Verify agent client was called correctly
            mock_chat.assert_called_once()
            call_args = mock_chat.call_args[0][0]
            assert isinstance(call_args, AgentChatRequest)
            assert call_args.message == "Hello, tell me about my hiking interests"
            assert call_args.user_id == "test-user-123"
            assert call_args.session_id == "test-session-123"
    
    def test_chat_endpoint_validation_errors(self, client):
        """Test chat endpoint validation"""
        # Test empty messages
        response = client.post("/v1/chat/", json={
            "messages": [],
            "user_id": "test-user-123"
        })
        assert response.status_code == 400
        assert "At least one message is required" in response.json()["detail"]
        
        # Test non-user latest message
        response = client.post("/v1/chat/", json={
            "messages": [
                {"role": "assistant", "content": "Hello"}
            ],
            "user_id": "test-user-123"
        })
        assert response.status_code == 400
        assert "Latest message must be from user" in response.json()["detail"]
    
    def test_chat_endpoint_agent_service_error(self, client, sample_chat_request):
        """Test handling of agent service errors"""
        with patch('luki_api.clients.agent_client.agent_client.chat') as mock_chat:
            # Test HTTP status error
            mock_chat.side_effect = httpx.HTTPStatusError(
                "Service error", 
                request=MagicMock(), 
                response=MagicMock(status_code=500)
            )
            
            response = client.post("/v1/chat/", json=sample_chat_request)
            assert response.status_code == 502
            assert "Agent service unavailable" in response.json()["detail"]
    
    def test_chat_endpoint_connection_error(self, client, sample_chat_request):
        """Test handling of agent service connection errors"""
        with patch('luki_api.clients.agent_client.agent_client.chat') as mock_chat:
            mock_chat.side_effect = httpx.RequestError("Connection failed")
            
            response = client.post("/v1/chat/", json=sample_chat_request)
            assert response.status_code == 503
            assert "Unable to connect to agent service" in response.json()["detail"]
    
    def test_streaming_endpoint_success(self, client, sample_chat_request):
        """Test successful streaming endpoint integration"""
        async def mock_stream():
            yield "Hello"
            yield " there!"
            yield " How"
            yield " can"
            yield " I"
            yield " help?"
        
        with patch('luki_api.clients.agent_client.agent_client.chat_stream') as mock_stream_chat:
            mock_stream_chat.return_value = mock_stream()
            
            response = client.post("/v1/chat/stream", json=sample_chat_request)
            
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream"
            
            # Parse streaming response
            content = response.text
            lines = content.strip().split('\n')
            
            # Verify streaming format
            data_lines = [line for line in lines if line.startswith('data: ')]
            assert len(data_lines) > 0
            
            # Verify tokens are streamed
            tokens = []
            for line in data_lines:
                if line.startswith('data: '):
                    try:
                        data = json.loads(line[6:])
                        if 'token' in data:
                            tokens.append(data['token'])
                    except json.JSONDecodeError:
                        pass
            
            # Should have received some tokens
            assert len(tokens) > 0
    
    def test_streaming_endpoint_validation_errors(self, client):
        """Test streaming endpoint validation"""
        # Test empty messages
        response = client.post("/v1/chat/stream", json={
            "messages": [],
            "user_id": "test-user-123"
        })
        
        assert response.status_code == 200
        content = response.text
        assert "At least one message is required" in content
    
    def test_conversation_history_context(self, client, mock_agent_response):
        """Test that conversation history is properly passed to agent"""
        chat_request = {
            "messages": [
                {"role": "user", "content": "What's my name?"},
                {"role": "assistant", "content": "Your name is John."},
                {"role": "user", "content": "What did I just ask you?"}
            ],
            "user_id": "test-user-123",
            "session_id": "test-session-123"
        }
        
        with patch('luki_api.clients.agent_client.agent_client.chat') as mock_chat:
            mock_chat.return_value = mock_agent_response
            
            response = client.post("/v1/chat/", json=chat_request)
            assert response.status_code == 200
            
            # Verify conversation history was passed correctly
            call_args = mock_chat.call_args[0][0]
            assert call_args.message == "What did I just ask you?"
            assert len(call_args.context["conversation_history"]) == 2
            assert call_args.context["conversation_history"][0]["content"] == "What's my name?"
            assert call_args.context["conversation_history"][1]["content"] == "Your name is John."
    
    def test_session_management(self, client, sample_chat_request, mock_agent_response):
        """Test session ID management"""
        # Test with existing session
        with patch('luki_api.clients.agent_client.agent_client.chat') as mock_chat:
            mock_chat.return_value = mock_agent_response
            
            response = client.post("/v1/chat/", json=sample_chat_request)
            assert response.status_code == 200
            
            data = response.json()
            assert data["session_id"] == "test-session-123"
        
        # Test without session (should get new one from agent)
        request_without_session = sample_chat_request.copy()
        del request_without_session["session_id"]
        
        with patch('luki_api.clients.agent_client.agent_client.chat') as mock_chat:
            mock_chat.return_value = mock_agent_response
            
            response = client.post("/v1/chat/", json=request_without_session)
            assert response.status_code == 200
            
            data = response.json()
            assert data["session_id"] == "test-session-123"  # From agent response
    
    @pytest.mark.asyncio
    async def test_agent_client_health_check(self):
        """Test agent client health check functionality"""
        with patch('httpx.AsyncClient.get') as mock_get:
            # Test healthy response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            client = AgentClient("http://localhost:9000")
            is_healthy = await client.health_check()
            assert is_healthy is True
            
            # Test unhealthy response
            mock_response.status_code = 500
            is_healthy = await client.health_check()
            assert is_healthy is False
            
            # Test connection error
            mock_get.side_effect = Exception("Connection failed")
            is_healthy = await client.health_check()
            assert is_healthy is False
            
            await client.close()
    
    @pytest.mark.asyncio
    async def test_agent_client_chat_method(self):
        """Test agent client chat method"""
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "response": "Test response",
                "session_id": "test-session",
                "metadata": {"test": "data"}
            }
            mock_post.return_value = mock_response
            
            client = AgentClient("http://localhost:9000")
            request = AgentChatRequest(
                message="Test message",
                user_id="test-user",
                session_id="test-session"
            )
            
            response = await client.chat(request)
            
            assert response.response == "Test response"
            assert response.session_id == "test-session"
            assert response.metadata == {"test": "data"}
            
            # Verify correct API call
            mock_post.assert_called_once_with(
                "http://localhost:9000/v1/chat",
                json={
                    "message": "Test message",
                    "user_id": "test-user",
                    "session_id": "test-session",
                    "context": {}
                },
                headers={"Content-Type": "application/json"}
            )
            
            await client.close()
    
    def test_end_to_end_integration(self, client):
        """Test complete end-to-end integration flow"""
        # This test would require actual services running
        # For now, we'll mock the entire flow
        
        with patch('luki_api.clients.agent_client.agent_client.chat') as mock_chat:
            mock_response = AgentChatResponse(
                response="Based on your ELR data, you enjoy mountain hiking and have visited 5 national parks.",
                session_id="e2e-session-123",
                metadata={
                    "retrieval_count": 5,
                    "ctx_tokens": 1850,
                    "tool_calls": 1,
                    "sources": ["hiking_log_2023.json", "travel_memories.json"]
                }
            )
            mock_chat.return_value = mock_response
            
            # Simulate a realistic conversation
            request = {
                "messages": [
                    {"role": "user", "content": "Tell me about my hiking experiences"}
                ],
                "user_id": "john-doe-123",
                "session_id": None  # New conversation
            }
            
            response = client.post("/v1/chat/", json=request)
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify rich, contextual response
            assert "mountain hiking" in data["message"]["content"]
            assert "national parks" in data["message"]["content"]
            assert data["metadata"]["retrieval_count"] == 5
            assert data["metadata"]["tool_calls"] == 1
            assert "sources" in data["metadata"]
