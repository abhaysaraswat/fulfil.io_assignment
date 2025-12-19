"""Celery application configuration."""
from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "product_importer",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.import_tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
