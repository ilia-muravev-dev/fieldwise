"""Celery application: Redis as broker and result backend, one queue, JSON only."""

from celery import Celery

from fieldwise.config import get_settings

settings = get_settings()

celery_app = Celery(
    "fieldwise",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["fieldwise.worker.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # OCR and model calls are long; do not hoard tasks
    task_default_queue="fieldwise",
    result_expires=24 * 3600,
)
