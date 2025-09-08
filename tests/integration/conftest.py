"""
Test fixtures for API Gateway integration tests.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from fastapi import FastAPI
from luki_api.routes import chat, elr, health, metrics
from luki_api.middleware import logging, metrics as metrics_middleware, rate_limit, tracing
from luki_api.middleware.tracing import RequestIDMiddleware
from luki_api.clients.memory_service import MemoryServiceClient

@pytest.fixture
def test_app(mock_memory_service):
    """
    Create a FastAPI app instance for testing with auth bypassed.
    
    Returns:
        FastAPI: A FastAPI app instance with authentication disabled for testing
    """
    from luki_api.routes.elr import get_memory_client
    
    app = FastAPI(
        title="LUKi API Gateway - Test",
        description="Test instance with auth disabled",
        version="1.0.0",
    )
    
    # Override memory service dependency with mock
    async def mock_get_memory_client():
        yield mock_memory_service
    
    app.dependency_overrides[get_memory_client] = mock_get_memory_client

    # Add middleware (excluding auth and rate limit middleware for tests)
    app.middleware("http")(logging.request_logging_middleware)
    app.middleware("http")(metrics_middleware.metrics_middleware)
    # Skip auth middleware for tests
    # Skip rate limit middleware for tests to avoid Redis dependency
    # Add tracing middleware for request ID generation
    app.add_middleware(tracing.RequestIDMiddleware)

    # Add test auth middleware that always passes
    @app.middleware("http")
    async def test_auth_middleware(request, call_next):
        # Set default auth state for tests
        request.state.auth_type = "test"
        request.state.auth_key = "test_api_key"
        request.state.user_id = "test_user"
        # Continue with request
        response = await call_next(request)
        return response

    # Include routers
    app.include_router(health.router, prefix="", tags=["health"])  # No prefix for health
    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
    app.include_router(elr.router, prefix="/v1/elr", tags=["elr"])
    app.include_router(metrics.router, prefix="/metrics", tags=["metrics"])

    @app.get("/")
    async def root():
        return {"message": "LUKi API Gateway - Test Mode"}

    return app

@pytest.fixture
def test_client(test_app):
    """
    Create a FastAPI test client.
    
    Returns:
        TestClient: A FastAPI test client instance for testing API endpoints
    """
    return TestClient(test_app)



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
    This fixture is now deprecated in favor of the test_app fixture.
    """
    # This fixture is kept for backward compatibility but is no longer needed
    # since we create a separate test app without the auth middleware
    pass
