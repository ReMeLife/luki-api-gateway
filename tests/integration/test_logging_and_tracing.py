"""
Integration tests for logging and request tracing functionality.
"""
import pytest
from fastapi.testclient import TestClient
import json
from unittest.mock import patch, MagicMock
import logging
from luki_api.config import settings

class TestLogging:
    """Test cases for API Gateway logging middleware"""
    
    def test_request_logging(self, test_client):
        """Test that requests are properly logged"""
        with patch("luki_api.middleware.logging.logger") as mock_logger:
            # Make a test request
            response = test_client.get(
                "/health",
                headers={"X-Request-ID": "test-request-id"}
            )
            
            # Verify response is successful
            assert response.status_code == 200
            
            # Verify logger was called (logging middleware is active)
            # Since logging middleware runs, we expect at least some logging calls
            assert mock_logger.info.called or mock_logger.debug.called
    
    def test_response_logging(self, test_client):
        """Test that responses are properly logged"""
        with patch("luki_api.middleware.logging.logger") as mock_logger:
            # Make a test request
            response = test_client.get("/health")
            
            # Verify response is successful
            assert response.status_code == 200
            
            # Verify logger was called (logging middleware is active)
            # Since logging middleware runs, we expect at least some logging calls
            assert mock_logger.info.called or mock_logger.debug.called
    
    def test_error_logging(self, test_client):
        """Test that errors are properly logged"""
        with patch("luki_api.middleware.logging.logger") as mock_logger:
            # Make a request to a non-existent endpoint to trigger 404
            response = test_client.get("/non_existent_path")
            
            # Verify error response
            assert response.status_code == 404
            
            # Verify logger was called (logging middleware is active)
            # For 404 errors, logging middleware should still log the request/response
            assert mock_logger.info.called or mock_logger.warning.called or mock_logger.error.called


class TestTracing:
    """Test cases for API Gateway request tracing"""
    
    def test_request_id_generation(self, test_client):
        """Test that request IDs are generated when not provided"""
        with patch("luki_api.middleware.tracing.request_id_middleware") as original_middleware:
            # Use the actual middleware
            from luki_api.middleware.tracing import request_id_middleware
            original_middleware.side_effect = request_id_middleware
            
            # Capture the response with the generated request ID
            response = test_client.get("/health")
            assert "X-Request-ID" in response.headers
            assert len(response.headers["X-Request-ID"]) > 0
    
    def test_request_id_propagation(self, test_client):
        """Test that provided request IDs are preserved and included in response"""
        with patch("luki_api.middleware.tracing.request_id_middleware") as original_middleware:
            # Use the actual middleware
            from luki_api.middleware.tracing import request_id_middleware
            original_middleware.side_effect = request_id_middleware
            
            # Provide a specific request ID
            request_id = "test-tracing-id-12345"
            response = test_client.get(
                "/health",
                headers={"X-Request-ID": request_id}
            )
            
            # Verify the same request ID is in the response
            assert "X-Request-ID" in response.headers
            assert response.headers["X-Request-ID"] == request_id
