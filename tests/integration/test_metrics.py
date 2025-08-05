"""
Test Metrics Endpoints and Middleware

Integration tests for the metrics collection functionality.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import re
from prometheus_client import REGISTRY

def test_metrics_endpoint(test_client: TestClient):
    """Test that the metrics endpoint returns Prometheus metrics"""
    response = test_client.get("/metrics/")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    
    # Verify some expected metrics are in the response
    content = response.text
    assert "http_requests_total" in content
    assert "http_request_duration_seconds" in content
    assert "process_" in content  # Prometheus automatically adds process metrics

def test_metrics_health_endpoint(test_client: TestClient):
    """Test the metrics health check endpoint"""
    response = test_client.get("/metrics/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "metrics_system": "operational"}

def test_request_metrics_collection(test_client: TestClient):
    """Test that requests are properly tracked in metrics"""
    # Make a request to an endpoint
    test_client.get("/health/")
    
    # Get metrics to check if the request was recorded
    response = test_client.get("/metrics/")
    content = response.text
    
    # Check that this request was counted in the http_requests_total metric
    assert re.search(r'http_requests_total{endpoint="/health/",method="GET",status="200"} [1-9]', content)
    
    # Check that request latency was measured
    assert re.search(r'http_request_duration_seconds_count{endpoint="/health/",method="GET"} [1-9]', content)

def test_error_metrics(test_client: TestClient):
    """Test that errors are properly tracked in metrics"""
    # Make a request to a non-existent endpoint to generate a 404 error
    test_client.get("/non-existent-path")
    
    # Get metrics to check if the error was recorded
    response = test_client.get("/metrics/")
    content = response.text
    
    # Check that this request was counted with status 404
    assert re.search(r'http_requests_total{endpoint="[^"]*",method="GET",status="404"} [1-9]', content)

def test_memory_service_metrics_tracking():
    """Test the memory service metrics tracking functions"""
    from luki_api.middleware.metrics import (
        track_memory_service_request,
        track_memory_service_latency,
        track_memory_service_error
    )
    
    # Record a mock memory service request
    method = "GET"
    endpoint = "/test"
    track_memory_service_request(method, endpoint)
    track_memory_service_latency(method, endpoint, 0.5)
    
    # Get the metric from the registry
    for metric in REGISTRY.collect():
        if metric.name == "memory_service_requests_total":
            for sample in metric.samples:
                if (sample.labels.get("method") == method and 
                    sample.labels.get("endpoint") == endpoint):
                    assert sample.value >= 1
                    break
            else:
                pytest.fail("Memory service request metric not found")
            break
    else:
        pytest.fail("memory_service_requests_total metric not found")
    
    # Record a mock error
    error_type = "ConnectionError"
    track_memory_service_error(method, endpoint, error_type)
    
    # Get the metric from the registry
    for metric in REGISTRY.collect():
        if metric.name == "memory_service_errors_total":
            for sample in metric.samples:
                if (sample.labels.get("method") == method and 
                    sample.labels.get("endpoint") == endpoint and
                    sample.labels.get("error_type") == error_type):
                    assert sample.value >= 1
                    break
            else:
                pytest.fail("Memory service error metric not found")
            break
    else:
        pytest.fail("memory_service_errors_total metric not found")

def test_session_tracking():
    """Test the user session tracking functions"""
    from luki_api.middleware.metrics import track_session_start, track_session_end
    
    # Get current value of active sessions
    initial_value = 0.0  # Default to 0.0 if not found
    for metric in REGISTRY.collect():
        if metric.name == "active_user_sessions":
            for sample in metric.samples:
                initial_value = sample.value
                break
            break
    
    # Track a new session
    track_session_start()
    
    # Check value increased
    for metric in REGISTRY.collect():
        if metric.name == "active_user_sessions":
            for sample in metric.samples:
                assert sample.value == (initial_value + 1)
                break
            break
    
    # End the session
    track_session_end()
    
    # Check value returned to initial
    for metric in REGISTRY.collect():
        if metric.name == "active_user_sessions":
            for sample in metric.samples:
                assert sample.value == initial_value
                break
            break
