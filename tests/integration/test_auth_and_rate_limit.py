"""
Integration tests for authentication and rate limiting.
"""
import pytest
from fastapi.testclient import TestClient
import json
from unittest.mock import patch
from luki_api.config import settings

class TestAuthentication:
    """Test cases for API Gateway authentication mechanisms"""
    
    def test_api_key_auth(self, test_client):
        """Test API key authentication flow"""
        # Test with valid API key
        response = test_client.get(
            "/v1/elr/items/user123",
            headers={settings.API_KEY_HEADER: "test_api_key"}
        )
        assert response.status_code != 401  # Should not get unauthorized
        
        # Test without API key
        with patch("luki_api.middleware.auth.auth_middleware") as original_middleware:
            # Use the actual middleware
            from luki_api.middleware.auth import auth_middleware
            original_middleware.side_effect = auth_middleware
            
            response = test_client.get("/v1/elr/items/user123")
            assert response.status_code == 401
            assert "Authentication required" in response.json()["detail"]
    
    def test_jwt_auth(self, test_client):
        """Test JWT authentication flow"""
        # Mock JWT verification to succeed
        with patch("luki_api.auth.jwt.JWTAuth.verify_token") as mock_verify:
            mock_verify.return_value = {
                "sub": "test_user",
                "roles": ["user"],
                "exp": 9999999999  # Far future
            }
            
            # Test with valid JWT
            response = test_client.get(
                "/v1/elr/items/test_user",
                headers={"Authorization": "Bearer test_jwt_token"}
            )
            assert response.status_code != 401  # Should not get unauthorized
        
        # Test with invalid JWT
        with patch("luki_api.middleware.auth.auth_middleware") as original_middleware:
            # Use the actual middleware
            from luki_api.middleware.auth import auth_middleware
            original_middleware.side_effect = auth_middleware
            
            # Provide invalid token
            response = test_client.get(
                "/v1/elr/items/test_user",
                headers={"Authorization": "Bearer invalid_token"}
            )
            assert response.status_code == 401
    
    def test_health_endpoint_no_auth(self, test_client):
        """Test that health endpoint is accessible without authentication"""
        with patch("luki_api.middleware.auth.auth_middleware") as original_middleware:
            # Use the actual middleware
            from luki_api.middleware.auth import auth_middleware
            original_middleware.side_effect = auth_middleware
            
            response = test_client.get("/health")
            assert response.status_code == 200
            assert response.json()["status"] == "healthy"


class TestRateLimiting:
    """Test cases for API Gateway rate limiting"""
    
    def test_rate_limiting(self, test_client):
        """Test rate limiting functionality"""
        with patch("luki_api.middleware.rate_limit.rate_limit_middleware") as mock_rate_limit:
            # Configure the mock to simulate rate limiting after 3 requests
            request_count = 0
            
            async def simulate_rate_limiting(request, call_next):
                nonlocal request_count
                request_count += 1
                if request_count > 3:
                    from fastapi import HTTPException
                    raise HTTPException(
                        status_code=429,
                        detail="Rate limit exceeded. Try again in 60 seconds."
                    )
                return await call_next(request)
            
            mock_rate_limit.side_effect = simulate_rate_limiting
            
            # Make multiple requests to trigger rate limiting
            for i in range(3):
                response = test_client.get(
                    "/v1/elr/items/user123",
                    headers={settings.API_KEY_HEADER: "test_api_key"}
                )
                assert response.status_code == 200
            
            # This request should be rate limited
            response = test_client.get(
                "/v1/elr/items/user123",
                headers={settings.API_KEY_HEADER: "test_api_key"}
            )
            assert response.status_code == 429
            assert "Rate limit exceeded" in response.json()["detail"]
