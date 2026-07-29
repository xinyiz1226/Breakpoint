from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import ensure_aware, utcnow
from app.models.cleanup import StorageCleanupTask
from app.models.enums import (
    ACTIVE_JOB_STATUSES,
    JobStatus,
    StorageCleanupOperation,
    StorageCleanupStatus,
    VideoAssetStatus,
)
from app.models.job import AnalysisJob, ExportJob
from app.models.project import Project
from app.models.user import User
from app.models.video import VideoAsset
from app.services import storage_cleanup
from app.services.storage import ObjectStorage


def _get_or_create_unbound_task(
    db: Session,
    *,
    project_id,
    object_key: str,
) -> StorageCleanupTask:
    task = db.execute(
        select(StorageCleanupTask).where(
            StorageCleanupTask.project_id == project_id,
            StorageCleanupTask.video_asset_id.is_(None),
            StorageCleanupTask.object_key == object_key,
            StorageCleanupTask.operation == StorageCleanupOperation.DELETE_OBJECT,
            StorageCleanupTask.status.in_(
                (
                    StorageCleanupStatus.PENDING,
                    StorageCleanupStatus.RUNNING,
                    StorageCleanupStatus.FAILED,
                    StorageCleanupStatus.COMPLETED,
                )
            ),
        )
    ).scalars().first()
    if task is None:
        task = storage_cleanup.get_or_create_cleanup_task(
            db,
            project_id=project_id,
            video_asset_id=None,
            object_key=object_key,
            upload_id=None,
            operation=StorageCleanupOperation.DELETE_OBJECT,
        )
    return task


def _cleanup_unbound_object(
    db: Session,
    storage: ObjectStorage,
    *,
    project_id,
    owner_id,
    object_key: str,
) -> bool:
    db.execute(select(User).where(User.id == owner_id).with_for_update()).scalar_one()
    db.execute(
        select(Project).where(Project.id == project_id).with_for_update()
    ).scalar_one()
    task = _get_or_create_unbound_task(
        db, project_id=project_id, object_key=object_key
    )
    db.commit()
    storage_cleanup.claim_and_process(db, task.id, storage)
    db.expire_all()
    return db.get(StorageCleanupTask, task.id).status == StorageCleanupStatus.COMPLETED


def run_retention_cleanup(
    db: Session,
    storage: ObjectStorage,
    *,
    now: datetime | None = None,
    limit: int = 50,
) -> int:
    reference = now or utcnow()
    processed = storage_cleanup.run_due_storage_cleanup_sweep(
        db, storage, now=reference, limit=limit
    )
    assets = db.execute(
        select(VideoAsset)
        .where(
            VideoAsset.retention_expires_at.is_not(None),
            VideoAsset.retention_expires_at <= reference,
            VideoAsset.status == VideoAssetStatus.UPLOADED,
        )
        .limit(limit)
    ).scalars().all()
    for candidate in assets:
        db.execute(
            select(User).where(User.id == candidate.owner_id).with_for_update()
        ).scalar_one()
        db.execute(
            select(Project).where(Project.id == candidate.project_id).with_for_update()
        ).scalar_one()
        asset = db.execute(
            select(VideoAsset)
            .where(VideoAsset.id == candidate.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one()
        if (
            asset.status != VideoAssetStatus.UPLOADED
            or asset.retention_expires_at is None
            or ensure_aware(asset.retention_expires_at) > ensure_aware(reference)
        ):
            db.commit()
            continue
        active_analyses = db.execute(
            select(AnalysisJob)
            .where(
                AnalysisJob.video_asset_id == asset.id,
                AnalysisJob.status.in_(list(ACTIVE_JOB_STATUSES)),
            )
            .order_by(AnalysisJob.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalars().all()
        active_exports = db.execute(
            select(ExportJob)
            .where(
                ExportJob.project_id == asset.project_id,
                ExportJob.status.in_(list(ACTIVE_JOB_STATUSES)),
            )
            .order_by(ExportJob.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalars().all()
        if active_analyses or active_exports:
            for analysis in active_analyses:
                if analysis.cancel_requested_at is None:
                    analysis.cancel_requested_at = reference
                    analysis.event_version += 1
            for export in active_exports:
                if export.status == JobStatus.QUEUED:
                    export.status = JobStatus.CANCELLED
                    export.lease_token = uuid.uuid4()
                    export.failure_summary = "Export cancelled because the source expired"
                    export.failure_detail = None
                    export.finished_at = reference
                    export.event_version += 1
                elif export.cancel_requested_at is None:
                    export.cancel_requested_at = reference
                    export.event_version += 1
            db.commit()
            continue
        asset.status = VideoAssetStatus.CLEANUP_PENDING
        task = storage_cleanup.get_or_create_cleanup_task(
            db,
            project_id=asset.project_id,
            video_asset_id=asset.id,
            object_key=asset.object_key,
            upload_id=None,
            operation=StorageCleanupOperation.DELETE_OBJECT,
            generation=asset.cleanup_generation,
        )
        preview_key = asset.preview_object_key
        preview_task = (
            _get_or_create_unbound_task(
                db,
                project_id=asset.project_id,
                object_key=preview_key,
            )
            if preview_key
            else None
        )
        # Both deletions are durable before either external call. A crash
        # after source deletion cannot orphan the preview.
        db.commit()
        storage_cleanup.claim_and_process(db, task.id, storage)
        if preview_task is not None:
            storage_cleanup.claim_and_process(db, preview_task.id, storage)
            db.expire_all()
        if (
            preview_task is not None
            and db.get(StorageCleanupTask, preview_task.id).status
            == StorageCleanupStatus.COMPLETED
        ):
            asset = db.get(VideoAsset, asset.id)
            asset.preview_object_key = None
            db.commit()
        processed += 1

    exports = db.execute(
        select(ExportJob)
        .where(
            ExportJob.status == JobStatus.SUCCEEDED,
            ExportJob.output_object_key.is_not(None),
            ExportJob.output_expires_at.is_not(None),
            ExportJob.output_expires_at <= reference,
        )
        .limit(limit)
    ).scalars().all()
    for export in exports:
        key = export.output_object_key
        assert key is not None
        if _cleanup_unbound_object(
            db,
            storage,
            project_id=export.project_id,
            owner_id=export.owner_id,
            object_key=key,
        ):
            export = db.get(ExportJob, export.id)
            export.output_object_key = None
            export.output_expires_at = None
            export.event_version += 1
            db.commit()
        processed += 1
    return processed
