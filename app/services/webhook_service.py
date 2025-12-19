"""Webhook service for triggering event notifications."""
import asyncio
import time
from typing import Any, Dict

import httpx
from sqlalchemy.orm import Session

from app.models.webhook import Webhook

# Supported webhook event types
WEBHOOK_EVENTS = [
    "product.created",
    "product.updated",
    "product.deleted",
    "import.started",
    "import.completed",
    "import.failed",
]


async def trigger_webhooks(
    event_type: str, payload: Dict[str, Any], db: Session
) -> None:
    """
    Send webhook to all enabled webhooks for this event type.
    Non-blocking, fire-and-forget.

    Args:
        event_type: Type of event (e.g., "product.created")
        payload: Event data to send
        db: Database session
    """
    # Get enabled webhooks for this event type
    webhooks = (
        db.query(Webhook)
        .filter(Webhook.event_type == event_type, Webhook.enabled == True)
        .all()
    )

    if not webhooks:
        return

    # Send webhooks asynchronously
    async with httpx.AsyncClient(timeout=5.0) as client:
        tasks = [_send_webhook(client, webhook.url, payload) for webhook in webhooks]
        # Gather all tasks, don't raise on exceptions
        await asyncio.gather(*tasks, return_exceptions=True)


async def _send_webhook(
    client: httpx.AsyncClient, url: str, payload: Dict[str, Any]
) -> None:
    """
    Send a single webhook request.

    Args:
        client: HTTP client
        url: Webhook URL
        payload: Event data
    """
    try:
        await client.post(url, json=payload)
    except Exception as e:
        # Log error but don't fail the main operation
        print(f"Failed to send webhook to {url}: {e}")


async def test_webhook(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Test a webhook by sending a sample payload and measuring response.

    Args:
        url: Webhook URL to test
        payload: Test payload

    Returns:
        Dict with test results including status code and response time
    """
    start_time = time.time()

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json=payload)
            response_time = time.time() - start_time

            return {
                "success": True,
                "status_code": response.status_code,
                "response_time": round(response_time, 3),
            }
    except httpx.TimeoutException:
        return {
            "success": False,
            "error": "Request timeout (> 5 seconds)",
            "response_time": 5.0,
        }
    except Exception as e:
        response_time = time.time() - start_time
        return {
            "success": False,
            "error": str(e),
            "response_time": round(response_time, 3),
        }
