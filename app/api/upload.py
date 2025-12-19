"""CSV upload API endpoints."""
import json
import uuid

import redis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from supabase import create_client

from app.config import get_settings
from app.database import get_db
from app.models.upload_job import UploadJob
from app.schemas.upload import (
    UploadCompleteRequest,
    UploadCompleteResponse,
    UploadInitiateRequest,
    UploadInitiateResponse,
    UploadJobResponse,
)
from app.tasks.import_tasks import process_csv_import

router = APIRouter(prefix="/api/upload", tags=["upload"])

settings = get_settings()


@router.post("/initiate", response_model=UploadInitiateResponse)
async def initiate_upload(
    request: UploadInitiateRequest, db: Session = Depends(get_db)
):
    """
    Create signed upload URL for direct frontend → Supabase upload.
    Returns immediately with signed URL and job_id (< 1 second).

    This endpoint creates a new upload job and generates a signed URL
    that the frontend can use to upload the CSV file directly to Supabase Storage,
    bypassing the backend to avoid timeout issues.
    """
    # 1. Create job record
    job_id = str(uuid.uuid4())
    job = UploadJob(id=job_id, filename=request.filename, status="pending")
    db.add(job)
    db.commit()

    # 2. Create signed upload URL (valid for 2 hours)
    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    storage_path = f"uploads/{job_id}.csv"

    try:
        signed_url_response = supabase.storage.from_("file").create_signed_upload_url(
            storage_path
        )

        # 3. Return signed URL and job_id (total time: < 1 second!)
        return UploadInitiateResponse(
            job_id=job_id,
            signed_url=signed_url_response["signedURL"],
            path=signed_url_response["path"],
        )
    except Exception as e:
        # Clean up job if signed URL creation fails
        db.delete(job)
        db.commit()
        raise HTTPException(
            status_code=500, detail=f"Failed to create signed URL: {str(e)}"
        )


@router.post("/complete", response_model=UploadCompleteResponse)
async def complete_upload(
    request: UploadCompleteRequest, db: Session = Depends(get_db)
):
    """
    Trigger background processing after frontend completes upload.
    Returns immediately (< 1 second).

    This endpoint is called by the frontend after successfully uploading
    the CSV to Supabase Storage. It triggers the Celery background task
    to process the CSV file.
    """
    # Verify job exists
    job = db.query(UploadJob).filter(UploadJob.id == request.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Update status and trigger Celery task
    job.status = "uploaded"
    db.commit()

    storage_path = f"uploads/{request.job_id}.csv"
    process_csv_import.delay(request.job_id, storage_path)

    return UploadCompleteResponse(job_id=request.job_id, status="processing")


@router.get("/{job_id}", response_model=UploadJobResponse)
async def get_upload_status(job_id: str, db: Session = Depends(get_db)):
    """
    Get upload job status and progress.

    This endpoint is used for polling-based progress tracking
    as a fallback when Server-Sent Events (SSE) are not available.
    """
    job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return job


@router.get("/{job_id}/stream")
async def stream_progress(job_id: str, db: Session = Depends(get_db)):
    """
    Server-Sent Events (SSE) endpoint for real-time progress streaming.

    This endpoint maintains an open connection and streams progress updates
    to the client in real-time as the CSV file is being processed.
    """
    # Verify job exists
    job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        """Generate SSE events from Redis pub/sub."""
        redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        pubsub = redis_client.pubsub()
        pubsub.subscribe(f"upload:{job_id}")

        try:
            for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    yield f"data: {json.dumps(data)}\n\n"

                    # Close connection when job is done
                    if data.get("status") in ["completed", "failed"]:
                        break
        finally:
            pubsub.unsubscribe(f"upload:{job_id}")
            redis_client.close()

    return StreamingResponse(event_generator(), media_type="text/event-stream")
