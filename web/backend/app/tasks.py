from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import or_, select

from app.celery_app import celery_app
from app.config import get_settings
from app.db import get_session_factory
from app.models.enums import JobStatus
from app.models.job import AnalysisJob, ExportJob
from app.models.base import utcnow
from app.services.media_processing import process_analysis_job, process_export_job
from app.services.media_tools import FakeMediaTools, RealMediaTools
from app.services.retention import run_retention_cleanup
from app.services.storage import S3ObjectStorage
from app.services.storage_cleanup import run_due_storage_cleanup_sweep


def _runtime():
    settings = get_settings()
    storage = S3ObjectStorage(settings)
    tools = (
        FakeMediaTools()
        if settings.media_tools_mode == "fake"
        else RealMediaTools(settings)
    )
    return settings, storage, tools


@celery_app.task(name="breakpoint.analysis", acks_late=True)
def analysis_task(job_id: str) -> None:
    settings, storage, tools = _runtime()
    process_analysis_job(
        get_session_factory(), storage, tools, uuid.UUID(job_id), settings=settings
    )


@celery_app.task(name="breakpoint.export", acks_late=True)
def export_task(job_id: str) -> None:
    settings, storage, tools = _runtime()
    process_export_job(
        get_session_factory(), storage, tools, uuid.UUID(job_id), settings=settings
    )


@celery_app.task(name="breakpoint.dispatch_queued_jobs")
def dispatch_queued_jobs() -> int:
    settings = get_settings()
    stale_before = utcnow() - timedelta(seconds=settings.job_stale_after_seconds)
    with get_session_factory()() as db:
        analysis_ids = list(
            db.execute(
                select(AnalysisJob.id)
                .where(
                    or_(
                        AnalysisJob.status == JobStatus.QUEUED,
                        (
                            (AnalysisJob.status == JobStatus.RUNNING)
                            & (
                                (AnalysisJob.heartbeat_at.is_(None))
                                | (AnalysisJob.heartbeat_at < stale_before)
                            )
                        ),
                    )
                )
                .limit(100)
            ).scalars()
        )
        export_ids = list(
            db.execute(
                select(ExportJob.id)
                .where(
                    or_(
                        ExportJob.status == JobStatus.QUEUED,
                        (
                            (ExportJob.status == JobStatus.RUNNING)
                            & (
                                (ExportJob.heartbeat_at.is_(None))
                                | (ExportJob.heartbeat_at < stale_before)
                            )
                        ),
                    )
                )
                .limit(100)
            ).scalars()
        )
    for job_id in analysis_ids:
        analysis_task.delay(str(job_id))
    for job_id in export_ids:
        export_task.delay(str(job_id))
    return len(analysis_ids) + len(export_ids)


@celery_app.task(name="breakpoint.storage_cleanup")
def storage_cleanup_task() -> int:
    settings = get_settings()
    with get_session_factory()() as db:
        return run_due_storage_cleanup_sweep(db, S3ObjectStorage(settings))


@celery_app.task(name="breakpoint.retention_cleanup")
def retention_cleanup_task() -> int:
    settings = get_settings()
    with get_session_factory()() as db:
        return run_retention_cleanup(db, S3ObjectStorage(settings))
