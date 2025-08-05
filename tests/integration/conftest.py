"""
Test fixtures for API Gateway integration tests.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from luki_api.main import app
from luki_api.clients.memory_service import MemoryServiceClient

@pytest.fixture
def test_client():
    """
    Create a FastAPI test client.
    
    Returns:
        TestClient: A FastAPI test client instance for testing API endpoints
    """
    return TestClient(app)

@pytest.fixture
def mock_memory_service():
    """
    Create a mock memory service client for testing ELR endpoints.
    
    Returns:
        AsyncMock: A mocked memory service client
    """
    mock_client = AsyncMock(spec=MemoryServiceClient)
    
    # Configure mock responses for common methods
    mock_client.get_elr_items.return_value = {
        "items": [
            {
                "id": "elr_12345",
                "content": "User enjoys hiking in the mountains",
                "user_id": "user123",
                "timestamp": "2025-08-05T15:30:00Z",
                "tags": ["interests", "outdoor_activities"],
                "metadata": {"source": "user_profile", "confidence": 0.95}
            }
        ],
        "total_count": 1
    }
    
    mock_client.create_elr_item.return_value = {
        "id": "elr_12345",
        "content": "User enjoys hiking in the mountains",
        "user_id": "user123",
        "timestamp": "2025-08-05T15:30:00Z",
        "tags": ["interests", "outdoor_activities"],
        "metadata": {"source": "user_profile", "confidence": 0.95}
    }
    
    mock_client.search_elr_items.return_value = {
        "items": [
            {
                "id": "elr_12345",
                "content": "User enjoys hiking in the mountains",
                "user_id": "user123",
                "timestamp": "2025-08-05T15:30:00Z",
                "tags": ["interests", "outdoor_activities"],
                "metadata": {"source": "user_profile", "confidence": 0.95}
            }
        ],
        "total_count": 1
    }
    
    return mock_client

@pytest.fixture
def mock_auth_middleware():
    """
    Mock the authentication middleware to bypass auth for tests.
    """
    with patch("luki_api.middleware.auth.auth_middleware") as mock_auth:
        async def _bypass_auth(request, call_next):
            # Set default auth state for tests
            request.state.auth_type = "test"
            request.state.auth_key = "test_api_key"
            request.state.user_id = "test_user"
            # Continue with request
            return await call_next(request)
            
        mock_auth.side_effect = _bypass_auth
        yield mock_auth
