#!/usr/bin/env python3

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

try:
    from luki_api.config import settings

    SECURITY_SERVICE_URL: Optional[str] = getattr(settings, "SECURITY_SERVICE_URL", None)
except Exception:
    import os

    SECURITY_SERVICE_URL = os.getenv("LUKI_SECURITY_SERVICE_URL")


logger = logging.getLogger(__name__)


async def enforce_policy_scopes(
    user_id: str,
    requested_scopes: List[str],
    requester_role: str = "api_gateway",
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Call the central security service to enforce consent/policy scopes.

    This is a thin wrapper around the /policy/enforce endpoint of
    luki-security-privacy. It is designed to fail-open when the
    security service is not configured, so existing behaviour is
    preserved until the environment is wired up.
    """
    if not requested_scopes:
        return {"allowed": True, "reason": "no_scopes_requested"}

    if not SECURITY_SERVICE_URL:
        logger.debug(
            "Security service URL not configured; skipping policy enforcement for user %s",
            user_id,
        )
        return {"allowed": True, "reason": "policy_disabled"}

    payload: Dict[str, Any] = {
        "user_id": user_id,
        "requester_role": requester_role,
        "requested_scopes": requested_scopes,
    }
    if context:
        payload["context"] = context

    url = SECURITY_SERVICE_URL.rstrip("/") + "/policy/enforce"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
        try:
            data = response.json()
        except ValueError:
            data = {"detail": response.text}

        if response.status_code == 200:
            allowed = bool(data.get("allowed", True))
            return {
                "allowed": allowed,
                "status_code": response.status_code,
                "reason": data.get("reason", "consent_valid"),
                "scopes_checked": data.get("scopes_checked", []),
                "detail": data.get("detail"),
            }

        logger.warning(
            "Policy enforcement denied or failed",
            extra={
                "user_id": user_id,
                "status_code": response.status_code,
                "data": data,
            },
        )
        return {
            "allowed": False,
            "status_code": response.status_code,
            "error": data.get("error", "policy_denied"),
            "detail": data.get("detail", data),
        }
    except Exception as exc:
        logger.error("Policy enforcement request failed", exc_info=exc)
        return {
            "allowed": False,
            "error": "policy_request_failed",
            "detail": str(exc),
        }
