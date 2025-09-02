"""
Integration tests for the ELR endpoints.
"""
import pytest
from fastapi.testclient import TestClient
import json
from unittest.mock import patch

class TestELREndpoints:
    """Test cases for ELR (Electronic Life Record) endpoints"""
    
    def test_get_elr_items(self, test_client, mock_memory_service):
        """Test retrieving ELR items for a specific user"""
        user_id = "user123"
        
        # Mock the memory client dependency
        with patch("luki_api.routes.elr.get_memory_client") as mock_get_client:
            mock_get_client.return_value.__enter__.return_value = mock_memory_service
            mock_get_client.return_value.__exit__.return_value = None
            
            # Call the endpoint
            response = test_client.get(f"/v1/elr/items/{user_id}")
            
            # Verify response
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert "total_count" in data
            assert data["total_count"] == 1
            assert len(data["items"]) == 1
            assert data["items"][0]["user_id"] == "user123"
            
            # Verify mock was called correctly
            mock_memory_service.get_elr_items.assert_called_once_with(
                user_id=user_id, limit=20
            )
    
    def test_create_elr_item(self, test_client, mock_memory_service):
        """Test creating a new ELR item"""
        # Test data
        item_data = {
            "content": "User enjoys hiking in the mountains",
            "user_id": "user123",
            "tags": ["interests", "outdoor_activities"],
            "metadata": {"source": "user_profile", "confidence": 0.95}
        }
        
        # Mock the memory client dependency
        with patch("luki_api.routes.elr.get_memory_client") as mock_get_client:
            mock_get_client.return_value.__enter__.return_value = mock_memory_service
            mock_get_client.return_value.__exit__.return_value = None
            
            # Call the endpoint
            response = test_client.post(
                "/v1/elr/items",
                json=item_data
            )
            
            # Verify response
            assert response.status_code == 201
            data = response.json()
            assert data["content"] == item_data["content"]
            assert data["user_id"] == item_data["user_id"]
            assert data["id"] == "elr_12345"  # ID from mock response
            
            # Verify mock was called with proper ELRItemRequest
            mock_memory_service.create_elr_item.assert_called_once()
            call_args = mock_memory_service.create_elr_item.call_args[0][0]
            assert call_args.content == item_data["content"]
            assert call_args.user_id == item_data["user_id"]
            assert call_args.tags == item_data["tags"]
    
    def test_search_elr_items(self, test_client, mock_memory_service):
        """Test searching for ELR items based on query text"""
        # Test data
        query_data = {
            "user_id": "user123",
            "query_text": "hiking mountains",
            "limit": 5
        }
        
        # Mock the memory client dependency
        with patch("luki_api.routes.elr.get_memory_client") as mock_get_client:
            mock_get_client.return_value.__enter__.return_value = mock_memory_service
            mock_get_client.return_value.__exit__.return_value = None
            
            # Call the endpoint
            response = test_client.post(
                "/v1/elr/search",
                json=query_data
            )
            
            # Verify response
            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert "total_count" in data
            assert data["total_count"] == 1
            assert len(data["items"]) == 1
            
            # Verify mock was called with proper ELRQueryRequest
            mock_memory_service.search_elr_items.assert_called_once()
            call_args = mock_memory_service.search_elr_items.call_args[0][0]
            assert call_args.user_id == query_data["user_id"]
            assert call_args.query_text == query_data["query_text"]
            assert call_args.limit == query_data["limit"]
    
    def test_update_elr_item(self, test_client, mock_memory_service):
        """Test updating an existing ELR item"""
        # Setup mock update response
        mock_memory_service.update_elr_item.return_value = {
            "id": "elr_12345",
            "content": "User enjoys mountain climbing and hiking",
            "user_id": "user123",
            "timestamp": "2025-08-05T16:30:00Z",
            "tags": ["interests", "outdoor_activities", "climbing"],
            "metadata": {"source": "user_profile", "confidence": 0.98}
        }
        
        # Test data
        item_id = "elr_12345"
        item_data = {
            "id": item_id,
            "content": "User enjoys mountain climbing and hiking",
            "user_id": "user123",
            "timestamp": "2025-08-05T16:30:00Z",
            "tags": ["interests", "outdoor_activities", "climbing"],
            "metadata": {"source": "user_profile", "confidence": 0.98}
        }
        
        # Mock the memory client dependency
        with patch("luki_api.routes.elr.get_memory_client") as mock_get_client:
            mock_get_client.return_value.__enter__.return_value = mock_memory_service
            mock_get_client.return_value.__exit__.return_value = None
            
            # Call the endpoint
            response = test_client.put(
                f"/v1/elr/items/{item_id}",
                json=item_data
            )
            
            # Verify response
            assert response.status_code == 200
            data = response.json()
            assert data["content"] == item_data["content"]
            assert "climbing" in data["tags"]
            assert data["metadata"]["confidence"] == 0.98
            
            # Verify mock was called correctly
            mock_memory_service.update_elr_item.assert_called_once()
            call_args = mock_memory_service.update_elr_item.call_args[0]
            assert call_args[0] == item_id
    
    def test_delete_elr_item(self, test_client, mock_memory_service):
        """Test deleting an ELR item"""
        item_id = "elr_12345"
        mock_memory_service.delete_elr_item.return_value = None
        
        # Mock the memory client dependency
        with patch("luki_api.routes.elr.get_memory_client") as mock_get_client:
            mock_get_client.return_value.__enter__.return_value = mock_memory_service
            mock_get_client.return_value.__exit__.return_value = None
            
            # Call the endpoint
            response = test_client.delete(f"/v1/elr/items/{item_id}")
            
            # Verify response
            assert response.status_code == 204
            
            # Verify mock was called correctly
            mock_memory_service.delete_elr_item.assert_called_once_with(item_id)
