from __future__ import annotations

from celery import Celery

from app.config import get_settings

settings = get_settings()
celery_app = Celery(
    "breakpoint",
    broker=settings.effective_celery_broker_url,
    backend=settings.effective_celery_result_backend,
    include=["app.tasks"],
)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_send_sent_event=True,
    worker_send_task_events=True,
    result_expires=86400,
    timezone="UTC",
    beat_schedule={
        "dispatch-queued-media-jobs": {
            "task": "breakpoint.dispatch_queued_jobs",
            "schedule": 30.0,
        },
        "due-storage-cleanup": {
            "task": "breakpoint.storage_cleanup",
            "schedule": float(settings.cleanup_sweep_seconds),
        },
        "source-export-retention": {
            "task": "breakpoint.retention_cleanup",
            "schedule": float(settings.retention_sweep_seconds),
        },
    },
)
