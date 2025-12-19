"""CSV processing service for batch import with UPSERT."""
import csv
import json
import logging
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
logger = logging.getLogger(__name__)


def process_csv_content(csv_content: str, job_id: str, db: Session) -> None:
    """
    Stream CSV from string content, validate, and batch insert with UPSERT.
    Updates progress every BATCH_SIZE rows.

    Args:
        csv_content: CSV file content as string
        job_id: Upload job ID for tracking progress
        db: Database session
    """
    logger.info(f"⚙️ Starting CSV content processing for job {job_id}")
    reader = csv.DictReader(StringIO(csv_content))
    batch = []
    total = 0
    created = 0
    updated = 0

    # Get job
    logger.info(f"📊 Looking up job record for processing: {job_id}")
    job = db.query(UploadJob).filter(UploadJob.id == job_id).first()
    if not job:
        logger.error(f"❌ Job not found for processing: {job_id}")
        raise ValueError(f"Job {job_id} not found")

    logger.info(f"✅ Found job for processing: total_rows={job.total_rows}")

    logger.info("🔄 Starting CSV row processing...")
    for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
        # Validate: sku and name required
        if not row.get("sku") or not row.get("name"):
            logger.warning(f"⚠️ Skipping invalid row {row_num}: missing sku or name")
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
            logger.info(f"📦 Processing batch of {len(batch)} products (total processed: {total})")
            created_count, updated_count = upsert_batch(batch, db)
            created += created_count
            updated += updated_count
            logger.info(f"✅ Batch processed: created={created_count}, updated={updated_count}")

            update_progress(job_id, total, created, updated, db)
            publish_progress(job_id, total, job.total_rows, created, updated, "processing")
            logger.info(f"📊 Progress updated: {total}/{job.total_rows} rows processed")
            batch = []

    # Process remaining batch
    if batch:
        logger.info(f"📦 Processing final batch of {len(batch)} products")
        created_count, updated_count = upsert_batch(batch, db)
        created += created_count
        updated += updated_count
        logger.info(f"✅ Final batch processed: created={created_count}, updated={updated_count}")

        update_progress(job_id, total, created, updated, db)

    # Final progress update
    logger.info(f"🏁 CSV processing completed for job {job_id}: total={total}, created={created}, updated={updated}")
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
        logger.debug("Empty batch, skipping upsert")
        return 0, 0

    # CRITICAL FIX: Deduplicate by SKU within batch (keep last occurrence)
    # PostgreSQL rejects UPSERT if same SKU appears multiple times in one INSERT
    unique_products = {}
    for product in products:
        unique_products[product["sku"]] = product

    # Convert back to list
    deduped_products = list(unique_products.values())

    # Log if duplicates were found
    duplicates_removed = len(products) - len(deduped_products)
    if duplicates_removed > 0:
        logger.warning(f"⚠️ Removed {duplicates_removed} duplicate SKUs within batch")

    batch_size = len(deduped_products)
    logger.debug(f"🔄 Starting upsert for batch of {batch_size} products (after deduplication)")

    # Check existing SKUs to count creates vs updates
    existing_skus = {p["sku"] for p in deduped_products}
    logger.debug(f"🔍 Checking {len(existing_skus)} SKUs for conflicts")

    existing_count = (
        db.query(Product).filter(func.lower(Product.sku).in_(existing_skus)).count()
    )
    logger.debug(f"📊 Found {existing_count} existing SKUs in batch")

    # PostgreSQL UPSERT
    logger.debug("⚡ Executing PostgreSQL UPSERT statement")
    stmt = insert(Product).values(deduped_products)
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

    created = batch_size - existing_count
    updated = existing_count
    logger.debug(f"✅ Upsert completed: created={created}, updated={updated}")
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
    job_id: str, processed: int, total: int, created: int, updated: int, status: str, error: str = None
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
        error: Error message (for failed status)
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
        if error:
            message["error"] = error
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
