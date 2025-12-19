"""CSV upload API endpoints."""
import asyncio
import json
import logging
import uuid
from pathlib import Path

import redis
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.upload_job import UploadJob
from app.schemas.upload import (
    UploadJobResponse,
    UploadResponse,
)
from app.tasks.import_tasks import process_csv_import

router = APIRouter(prefix="/api/upload", tags=["upload"])

settings = get_settings()

# Create temp directory for file uploads
TEMP_DIR = Path("/tmp/uploads")
TEMP_DIR.mkdir(exist_ok=True)





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
    Uses async Redis operations to avoid blocking other requests.
    """
    # Verify job exists
    job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        """Generate SSE events from Redis pub/sub with async operations."""
        redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        pubsub = redis_client.pubsub()
        pubsub.subscribe(f"upload:{job_id}")

        try:
            while True:
                # Non-blocking message check with timeout
                message = pubsub.get_message(timeout=1.0)

                if message and message["type"] == "message":
                    data = json.loads(message["data"])
                    yield f"data: {json.dumps(data)}\n\n"

                    # Close connection when job is done
                    if data.get("status") in ["completed", "failed"]:
                        break

                # Allow other async operations to run
                await asyncio.sleep(0.1)

        except Exception as e:
            # Log error but don't crash the stream
            logger.warning(f"SSE stream error for job {job_id}: {str(e)}")
            yield f"data: {json.dumps({'status': 'error', 'error': 'Stream error'})}\n\n"

        finally:
            pubsub.unsubscribe(f"upload:{job_id}")
            redis_client.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("", response_model=UploadResponse)
async def upload_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Direct CSV file upload endpoint.
    Handles large files efficiently by streaming and background processing.

    This endpoint:
    1. Accepts file upload immediately (< 30 seconds)
    2. Saves file to temporary storage
    3. Creates upload job record
    4. Triggers background processing with Celery
    5. Returns job_id for progress tracking

    Perfect for handling 500k+ record CSV files on platforms with timeout limits.
    """
    logger = logging.getLogger(__name__)

    logger.info(f"📁 Starting CSV upload: filename={file.filename}, content_type={file.content_type}")

    # Validate file type
    if not file.filename.lower().endswith('.csv'):
        logger.warning(f"❌ Invalid file type: {file.filename}")
        raise HTTPException(status_code=400, detail="Only CSV files are allowed")

    logger.info("✅ File type validation passed")

    # Validate file size (max 100MB to prevent abuse)
    logger.info("🔍 Starting file size validation...")
    file_size = 0
    content = await file.read(1024)  # Read first 1KB
    while content:
        file_size += len(content)
        if file_size > 100 * 1024 * 1024:  # 100MB limit
            logger.warning(f"❌ File too large: {file_size} bytes")
            raise HTTPException(status_code=413, detail="File too large (max 100MB)")
        content = await file.read(1024)

    logger.info(f"✅ File size validation passed: {file_size} bytes")

    # Reset file pointer
    await file.seek(0)

    # Create job record
    job_id = str(uuid.uuid4())
    logger.info(f"🆔 Created job ID: {job_id}")

    job = UploadJob(id=job_id, filename=file.filename, status="uploading")
    db.add(job)
    db.commit()
    logger.info(f"💾 Job record created in database: status=uploading")

    try:
        # Save file to temp storage
        temp_file_path = TEMP_DIR / f"{job_id}.csv"
        logger.info(f"💾 Starting file save to: {temp_file_path}")

        bytes_written = 0
        with open(temp_file_path, "wb") as buffer:
            # Stream file in chunks to handle large files
            content = await file.read(8192)  # 8KB chunks
            while content:
                buffer.write(content)
                bytes_written += len(content)
                content = await file.read(8192)

        logger.info(f"✅ File saved successfully: {bytes_written} bytes written")

        # Update job status and trigger background processing
        job.status = "uploaded"
        db.commit()
        logger.info("📊 Job status updated to 'uploaded'")

        # Process CSV in background (will take 3-5 minutes for 500k records)
        logger.info("🚀 Triggering Celery background task...")
        process_csv_import.delay(job_id, str(temp_file_path))
        logger.info("✅ Celery task triggered successfully")

        logger.info(f"🎉 Upload completed successfully for job {job_id}")

        return UploadResponse(
            job_id=job_id,
            status="processing",
            message="File uploaded successfully, processing in background"
        )

    except Exception as e:
        logger.error(f"💥 Upload failed for job {job_id}: {str(e)}", exc_info=True)

        # Clean up on error
        db.delete(job)
        db.commit()
        logger.info(f"🧹 Cleaned up job record from database: {job_id}")

        # Clean up temp file if it exists
        temp_file_path = TEMP_DIR / f"{job_id}.csv"
        if temp_file_path.exists():
            temp_file_path.unlink()
            logger.info(f"🧹 Cleaned up temp file: {temp_file_path}")

        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
