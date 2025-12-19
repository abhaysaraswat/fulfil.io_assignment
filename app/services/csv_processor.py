"""CSV processing service for batch import with UPSERT."""
import csv
import json
from io import StringIO

import redis
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.product import Product
from app.models.upload_job import UploadJob

BATCH_SIZE = 1000

settings = get_settings()


def process_csv_content(csv_content: str, job_id: str, db: Session) -> None:
    """
    Stream CSV from string content, validate, and batch insert with UPSERT.
    Updates progress every BATCH_SIZE rows.

    Args:
        csv_content: CSV file content as string
        job_id: Upload job ID for tracking progress
        db: Database session
    """
    reader = csv.DictReader(StringIO(csv_content))
    batch = []
    total = 0
    created = 0
    updated = 0

    # Get job
    job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
    if not job:
        raise ValueError(f"Job {job_id} not found")

    for row in reader:
        # Validate: sku and name required
        if not row.get("sku") or not row.get("name"):
            continue

        # Normalize SKU to lowercase
        product_data = {
            "sku": row["sku"].strip().lower(),
            "name": row["name"].strip(),
            "description": row.get("description", "").strip() or None,
            "active": True,
        }

        batch.append(product_data)
        total += 1

        if len(batch) >= BATCH_SIZE:
            created_count, updated_count = upsert_batch(batch, db)
            created += created_count
            updated += updated_count
            update_progress(job_id, total, created, updated, db)
            publish_progress(job_id, total, job.total_rows, created, updated, "processing")
            batch = []

    # Process remaining batch
    if batch:
        created_count, updated_count = upsert_batch(batch, db)
        created += created_count
        updated += updated_count
        update_progress(job_id, total, created, updated, db)

    # Final progress update
    publish_progress(job_id, total, total, created, updated, "completed")


def upsert_batch(products: list, db: Session) -> tuple[int, int]:
    """
    PostgreSQL INSERT ... ON CONFLICT DO UPDATE.
    Case-insensitive SKU matching using the unique index.

    Args:
        products: List of product dictionaries
        db: Database session

    Returns:
        Tuple of (created_count, updated_count)
    """
    if not products:
        return 0, 0

    # Check existing SKUs to count creates vs updates
    existing_skus = {p["sku"] for p in products}
    existing_count = (
        db.query(Product).filter(func.lower(Product.sku).in_(existing_skus)).count()
    )

    # PostgreSQL UPSERT
    stmt = insert(Product).values(products)
    stmt = stmt.on_conflict_do_update(
        index_elements=["sku"],  # Uses the LOWER(sku) unique index
        set_={
            "name": stmt.excluded.name,
            "description": stmt.excluded.description,
            "updated_at": func.now(),
        },
    )
    db.execute(stmt)
    db.commit()

    created = len(products) - existing_count
    updated = existing_count
    return created, updated


def update_progress(
    job_id: str, processed: int, created: int, updated: int, db: Session
) -> None:
    """
    Update job progress in database.

    Args:
        job_id: Upload job ID
        processed: Number of rows processed
        created: Number of products created
        updated: Number of products updated
        db: Database session
    """
    job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
    if job:
        job.processed_rows = processed
        job.created_rows = created
        job.updated_rows = updated
        db.commit()


def publish_progress(
    job_id: str, processed: int, total: int, created: int, updated: int, status: str
) -> None:
    """
    Publish progress to Redis pub/sub for real-time SSE streaming.

    Args:
        job_id: Upload job ID
        processed: Number of rows processed
        total: Total number of rows
        created: Number of products created
        updated: Number of products updated
        status: Current status (processing, completed, failed)
    """
    try:
        redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        message = {
            "job_id": job_id,
            "status": status,
            "processed": processed,
            "total": total,
            "created": created,
            "updated": updated,
        }
        redis_client.publish(f"upload:{job_id}", json.dumps(message))
    except Exception as e:
        # Don't fail the import if Redis is unavailable
        print(f"Failed to publish progress: {e}")


def count_csv_rows(csv_content: str) -> int:
    """
    Count total rows in CSV (excluding header).

    Args:
        csv_content: CSV file content as string

    Returns:
        Number of data rows
    """
    reader = csv.DictReader(StringIO(csv_content))
    return sum(1 for _ in reader)
