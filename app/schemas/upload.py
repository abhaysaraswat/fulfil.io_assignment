"""Upload request and response schemas."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UploadInitiateRequest(BaseModel):
    """Request to initiate CSV upload."""

    filename: str = Field(..., min_length=1, max_length=500)


class UploadInitiateResponse(BaseModel):
    """Response with signed URL for upload."""

    job_id: str
    signed_url: str
    path: str
    message: str = "Upload CSV to signed_url, then call /upload/complete"


class UploadCompleteRequest(BaseModel):
    """Request to complete upload and start processing."""

    job_id: str


class UploadCompleteResponse(BaseModel):
    """Response after triggering background processing."""

    job_id: str
    status: str
    message: str = "CSV processing started"


class UploadJobResponse(BaseModel):
    """Upload job status response."""

    id: UUID
    filename: str
    status: str
    total_rows: int
    processed_rows: int
    created_rows: int
    updated_rows: int
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
