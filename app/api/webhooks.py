"""Webhook CRUD API endpoints."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.webhook import Webhook
from app.schemas.webhook import (
    WebhookCreate,
    WebhookResponse,
    WebhookTestResponse,
    WebhookUpdate,
)
from app.services.webhook_service import test_webhook

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.get("", response_model=List[WebhookResponse])
def list_webhooks(db: Session = Depends(get_db)):
    """
    List all webhooks.

    Returns all configured webhooks with their settings.
    """
    webhooks = db.query(Webhook).order_by(Webhook.created_at.desc()).all()
    return webhooks


@router.post("", response_model=WebhookResponse, status_code=201)
def create_webhook(webhook: WebhookCreate, db: Session = Depends(get_db)):
    """
    Create a new webhook.

    Creates a webhook that will be triggered when the specified event type occurs.
    """
    db_webhook = Webhook(
        url=webhook.url, event_type=webhook.event_type, enabled=webhook.enabled
    )
    db.add(db_webhook)
    db.commit()
    db.refresh(db_webhook)

    return db_webhook


@router.get("/{webhook_id}", response_model=WebhookResponse)
def get_webhook(webhook_id: int, db: Session = Depends(get_db)):
    """
    Get a single webhook by ID.

    Args:
        webhook_id: ID of the webhook to retrieve
    """
    webhook = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    return webhook


@router.put("/{webhook_id}", response_model=WebhookResponse)
def update_webhook(
    webhook_id: int, webhook_update: WebhookUpdate, db: Session = Depends(get_db)
):
    """
    Update a webhook.

    Only provided fields will be updated.

    Args:
        webhook_id: ID of the webhook to update
        webhook_update: Updated webhook data
    """
    db_webhook = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not db_webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    # Update fields
    if webhook_update.url is not None:
        db_webhook.url = webhook_update.url
    if webhook_update.event_type is not None:
        db_webhook.event_type = webhook_update.event_type
    if webhook_update.enabled is not None:
        db_webhook.enabled = webhook_update.enabled

    db.commit()
    db.refresh(db_webhook)

    return db_webhook


@router.delete("/{webhook_id}", status_code=204)
def delete_webhook(webhook_id: int, db: Session = Depends(get_db)):
    """
    Delete a webhook.

    Args:
        webhook_id: ID of the webhook to delete
    """
    webhook = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    db.delete(webhook)
    db.commit()

    return None


@router.post("/{webhook_id}/test", response_model=WebhookTestResponse)
async def test_webhook_endpoint(webhook_id: int, db: Session = Depends(get_db)):
    """
    Test a webhook by sending a sample payload.

    Sends a test event to the webhook URL and returns the response status.

    Args:
        webhook_id: ID of the webhook to test
    """
    webhook = db.query(Webhook).filter(Webhook.id == webhook_id).first()
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    # Create sample test payload
    test_payload = {
        "event": webhook.event_type,
        "test": True,
        "data": {
            "id": 1,
            "sku": "TEST-SKU-001",
            "name": "Test Product",
            "description": "This is a test webhook event",
            "active": True,
        },
    }

    # Test the webhook
    result = await test_webhook(webhook.url, test_payload)

    return WebhookTestResponse(**result)
