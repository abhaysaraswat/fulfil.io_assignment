"""Webhook request and response schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class WebhookBase(BaseModel):
    """Base webhook schema."""

    url: str = Field(..., min_length=1, max_length=2048)
    event_type: str = Field(..., min_length=1, max_length=100)
    enabled: bool = True


class WebhookCreate(WebhookBase):
    """Schema for creating a webhook."""

    pass


class WebhookUpdate(BaseModel):
    """Schema for updating a webhook."""

    url: Optional[str] = Field(None, min_length=1, max_length=2048)
    event_type: Optional[str] = Field(None, min_length=1, max_length=100)
    enabled: Optional[bool] = None


class WebhookResponse(WebhookBase):
    """Schema for webhook responses."""

    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WebhookTestResponse(BaseModel):
    """Response from webhook test."""

    success: bool
    status_code: Optional[int] = None
    error: Optional[str] = None
    response_time: Optional[float] = None
