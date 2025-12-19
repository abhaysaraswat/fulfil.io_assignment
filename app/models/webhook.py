"""Webhook model for event notifications."""
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class Webhook(Base):
    """Model for webhook configurations."""

    __tablename__ = "webhooks"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(2048), nullable=False)
    event_type = Column(String(100), nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
