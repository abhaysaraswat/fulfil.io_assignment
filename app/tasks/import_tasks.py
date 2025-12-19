"""Celery tasks for CSV import processing."""
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
    db = SessionLocal()

    try:
        # Update status to processing
        job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        job.status = "processing"
        db.commit()

        # Trigger import.started webhook
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

        # Read CSV from local file (no Supabase needed!)
        with open(file_path, 'r', encoding='utf-8') as f:
            csv_content = f.read()

        # Count total rows for progress tracking
        total_rows = count_csv_rows(csv_content)
        job.total_rows = total_rows
        db.commit()

        # Process CSV in batches
        process_csv_content(csv_content, job_id, db)

        # Mark complete
        job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
        job.status = "completed"
        db.commit()

        # Trigger import.completed webhook
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

        return {
            "status": "completed",
            "job_id": job_id,
            "total_rows": job.total_rows,
            "created": job.created_rows,
            "updated": job.updated_rows,
        }

    except Exception as e:
        # Mark failed
        job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.error_message = str(e)
            db.commit()

        # Publish failure to Redis for SSE
        from app.services.csv_processor import publish_progress

        publish_progress(job_id, 0, 0, 0, 0, "failed")

        # Trigger import.failed webhook
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

        raise

    finally:
        db.close()
        # Clean up temp file after processing
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            pass  # Ignore cleanup errors
