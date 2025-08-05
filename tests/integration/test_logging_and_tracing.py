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
        with patch("luki_api.middleware.logging.logging") as mock_logging:
            # Setup mock logger
            mock_logger = MagicMock()
            mock_logging.getLogger.return_value = mock_logger
            
            # Make a test request
            response = test_client.get(
                "/health",
                headers={"X-Request-ID": "test-request-id"}
            )
            
            # Verify logger was called with request info
            assert mock_logger.info.called
            # Check for the call that logs the request
            request_log_found = False
            for call in mock_logger.info.call_args_list:
                args, _ = call
                if len(args) > 0 and isinstance(args[0], str) and "Received request" in args[0]:
                    request_log_found = True
                    break
            assert request_log_found
    
    def test_response_logging(self, test_client):
        """Test that responses are properly logged"""
        with patch("luki_api.middleware.logging.logging") as mock_logging:
            # Setup mock logger
            mock_logger = MagicMock()
            mock_logging.getLogger.return_value = mock_logger
            
            # Make a test request
            response = test_client.get("/health")
            
            # Verify logger was called with response info
            assert mock_logger.info.called
            # Check for the call that logs the response
            response_log_found = False
            for call in mock_logger.info.call_args_list:
                args, _ = call
                if len(args) > 0 and isinstance(args[0], str) and "Sending response" in args[0]:
                    response_log_found = True
                    break
            assert response_log_found
    
    def test_error_logging(self, test_client):
        """Test that errors are properly logged"""
        # Create a route that raises an exception
        with patch("luki_api.middleware.logging.logging") as mock_logging:
            # Setup mock logger
            mock_logger = MagicMock()
            mock_logging.getLogger.return_value = mock_logger
            
            # Make a request to a non-existent endpoint to trigger 404
            response = test_client.get("/non_existent_path")
            
            # Verify logger was called with error info
            assert mock_logger.error.called or mock_logger.warning.called
            
            # Check for error status code in response
            assert response.status_code == 404


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
