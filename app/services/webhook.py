"""POST job result to Node.js webhook_url (async httpx)."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


async def fire_webhook(webhook_url: str, payload: dict) -> None:
    """Send POST to webhook_url with job result. Best-effort; log errors."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(webhook_url, json=payload)
            r.raise_for_status()
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        logger.warning("Webhook POST failed: %s", e)
