"""Celery tasks for CSV import processing."""
import logging
import os
import asyncio
from pathlib import Path

from app.config import get_settings
from app.database import SessionLocal
from app.models.upload_job import UploadJob
from app.services.csv_processor import count_csv_rows, process_csv_content
from app.services.webhook_service import trigger_webhooks
from app.tasks.celery_app import celery_app

settings = get_settings()
logger = logging.getLogger(__name__)


@celery_app.task(bind=True)
def process_csv_import(self, job_id: str, file_path: str) -> dict:
    """
    Process CSV file from local storage in background.
    Can take 3-5 minutes for 500K rows.
    This runs in Celery worker, NOT in web request context.

    Args:
        self: Celery task instance
        job_id: Upload job ID
        file_path: Local path to CSV file

    Returns:
        Dict with job status and counts
    """
    logger.info(f"🚀 Starting CSV import task: job_id={job_id}, file_path={file_path}")

    db = SessionLocal()
    logger.info(f"🔌 Database connection established for job {job_id}")

    try:
        # Update status to processing
        logger.info(f"📊 Looking up job record: {job_id}")
        job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
        if not job:
            logger.error(f"❌ Job not found in database: {job_id}")
            raise ValueError(f"Job {job_id} not found")

        logger.info(f"✅ Found job record: filename={job.filename}, current_status={job.status}")

        job.status = "processing"
        db.commit()
        logger.info(f"📊 Job status updated to 'processing' for job {job_id}")

        # Trigger import.started webhook
        logger.info(f"🪝 Triggering import.started webhook for job {job_id}")
        asyncio.run(
            trigger_webhooks(
                "import.started",
                {
                    "event": "import.started",
                    "data": {"job_id": job_id, "filename": job.filename},
                },
                db,
            )
        )
        logger.info(f"✅ Import.started webhook triggered for job {job_id}")

        # Check if file exists
        if not os.path.exists(file_path):
            logger.error(f"❌ CSV file not found: {file_path}")
            raise FileNotFoundError(f"CSV file not found: {file_path}")

        file_size = os.path.getsize(file_path)
        logger.info(f"📁 Found CSV file: {file_path} ({file_size} bytes)")

        # Read CSV from local file (no Supabase needed!)
        logger.info(f"📖 Reading CSV content from file: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            csv_content = f.read()

        content_length = len(csv_content)
        logger.info(f"✅ CSV content loaded: {content_length} characters")

        # Count total rows for progress tracking
        logger.info("🔢 Counting total CSV rows...")
        total_rows = count_csv_rows(csv_content)
        job.total_rows = total_rows
        db.commit()
        logger.info(f"✅ Total rows counted: {total_rows} for job {job_id}")

        # Process CSV in batches
        logger.info(f"⚙️ Starting CSV processing in batches for job {job_id}")
        process_csv_content(csv_content, job_id, db)
        logger.info(f"✅ CSV processing completed for job {job_id}")

        # Mark complete
        logger.info(f"🏁 Marking job as completed: {job_id}")
        job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
        job.status = "completed"
        db.commit()
        logger.info(f"✅ Job marked as completed: created={job.created_rows}, updated={job.updated_rows}")

        # Trigger import.completed webhook
        logger.info(f"🪝 Triggering import.completed webhook for job {job_id}")
        asyncio.run(
            trigger_webhooks(
                "import.completed",
                {
                    "event": "import.completed",
                    "data": {
                        "job_id": job_id,
                        "filename": job.filename,
                        "total_rows": job.total_rows,
                        "created": job.created_rows,
                        "updated": job.updated_rows,
                    },
                },
                db,
            )
        )
        logger.info(f"✅ Import.completed webhook triggered for job {job_id}")

        result = {
            "status": "completed",
            "job_id": job_id,
            "total_rows": job.total_rows,
            "created": job.created_rows,
            "updated": job.updated_rows,
        }
        logger.info(f"🎉 Task completed successfully: {result}")
        return result

    except Exception as e:
        logger.error(f"💥 Task failed for job {job_id}: {str(e)}", exc_info=True)

        # Mark failed
        logger.info(f"📊 Marking job as failed: {job_id}")
        job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.error_message = str(e)
            db.commit()
            logger.info(f"✅ Job marked as failed in database: {job_id}")

        # Publish failure to Redis for SSE
        logger.info(f"📡 Publishing failure status to Redis for job {job_id}")
        from app.services.csv_processor import publish_progress
        publish_progress(job_id, 0, 0, 0, 0, "failed", str(e))
        logger.info(f"✅ Failure status with error published to Redis for job {job_id}")

        # Trigger import.failed webhook
        logger.info(f"🪝 Triggering import.failed webhook for job {job_id}")
        asyncio.run(
            trigger_webhooks(
                "import.failed",
                {
                    "event": "import.failed",
                    "data": {"job_id": job_id, "error": str(e)},
                },
                db,
            )
        )
        logger.info(f"✅ Import.failed webhook triggered for job {job_id}")

        logger.error(f"💥 Task failed completely for job {job_id}: {str(e)}")
        raise

    finally:
        logger.info(f"🔌 Closing database connection for job {job_id}")
        db.close()

        # Clean up temp file after processing
        logger.info(f"🧹 Cleaning up temp file: {file_path}")
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"✅ Temp file cleaned up: {file_path}")
            else:
                logger.warning(f"⚠️ Temp file not found for cleanup: {file_path}")
        except Exception as cleanup_error:
            logger.warning(f"⚠️ Failed to clean up temp file {file_path}: {str(cleanup_error)}")
