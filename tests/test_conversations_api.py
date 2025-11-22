from __future__ import annotations

from typing import Any, Dict

from fastapi.testclient import TestClient
import pytest

from luki_api.main import app
import luki_api.routes.conversations as conversations_module
import luki_api.config as gateway_config
import luki_api.middleware.rate_limit as rate_limit_module


@pytest.fixture(autouse=True)
def reset_in_memory_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure tests run against the in-memory conversations backend.

    We explicitly disable Supabase and clear the in-memory store so tests are
    deterministic and do not require external services.
    """
    monkeypatch.setattr(conversations_module, "supabase", None)
    conversations_module.conversations_store.clear()
    yield
    conversations_module.conversations_store.clear()


@pytest.fixture(autouse=True)
def disable_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable Redis-backed rate limiting for tests.

    This ensures conversation API tests do not depend on a running Redis
    instance or interact with a closed event loop.
    """
    monkeypatch.setattr(gateway_config.settings, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(rate_limit_module, "redis_client", None)


def test_create_and_list_conversations_in_memory() -> None:
    client = TestClient(app)

    user_id = "test-user-123"
    payload: Dict[str, Any] = {
        "title": "My Chat",
        "first_message": "Hello LUKi",
    }

    # Create a new conversation
    resp = client.post(f"/api/conversations/{user_id}", json=payload)
    assert resp.status_code == 201
    conv = resp.json()

    assert conv["user_id"] == user_id
    assert conv["id"]
    assert conv["message_count"] == 1
    assert conv["preview"].startswith("Hello LUKi")

    # List conversations for the user
    list_resp = client.get(f"/api/conversations/{user_id}")
    assert list_resp.status_code == 200
    data = list_resp.json()

    assert data["total"] == 1
    assert len(data["conversations"]) == 1
    assert data["conversations"][0]["id"] == conv["id"]


def test_add_and_get_messages_in_memory() -> None:
    client = TestClient(app)

    user_id = "test-user-123"

    # Create a conversation with a first user message
    create_resp = client.post(
        f"/api/conversations/{user_id}",
        json={"title": "My Chat", "first_message": "Hello LUKi"},
    )
    assert create_resp.status_code == 201
    conv_id = create_resp.json()["id"]

    # Add an assistant message
    msg_payload = {
        "role": "assistant",
        "content": "Hi there!",
        "timestamp": "2025-10-03T06:00:00Z",
    }
    add_resp = client.post(
        f"/api/conversations/{user_id}/{conv_id}/messages", json=msg_payload
    )
    assert add_resp.status_code == 200
    updated = add_resp.json()

    assert updated["id"] == conv_id
    assert updated["message_count"] == 2

    # Fetch messages via the messages endpoint (in-memory path)
    messages_resp = client.get(f"/api/conversations/{user_id}/messages/{conv_id}")
    assert messages_resp.status_code == 200
    data = messages_resp.json()

    assert data["conversation_id"] == conv_id
    assert data["total"] == 2
    roles = [m["role"] for m in data["messages"]]
    assert "user" in roles
    assert "assistant" in roles
