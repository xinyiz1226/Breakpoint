"""Project CRUD, strictly scoped to the authenticated owner.

Every lookup filters by ``owner_id`` in the same query used for the 404
check, so a project belonging to another user is indistinguishable from a
nonexistent one -- no ownership information leaks through status codes.

Deletion is a soft tombstone (``Project.deleted_at``), not a hard
``db.delete``: child rows (video asset, jobs), ledger history, and cleanup
tasks all survive for audit and durable cleanup. Every owner-facing lookup
here (and in ``uploads.py``) excludes tombstoned projects; only the
read-only admin API may still see them.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, get_storage
from app.models.base import utcnow
from app.models.cleanup import StorageCleanupTask
from app.models.enums import (
    ACTIVE_JOB_STATUSES,
    JobStatus,
    QuotaLedgerEventType,
    StorageCleanupOperation,
    VideoAssetStatus,
)
from app.models.job import AnalysisJob, ExportJob
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services import quota as quota_service
from app.services import reservations as reservation_service
from app.services import storage_cleanup as storage_cleanup_service
from app.services.storage import ObjectStorage

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def _get_owned_project(
    db: Session, project_id: uuid.UUID, owner_id: uuid.UUID, *, for_update: bool = False
) -> Project:
    stmt = select(Project).where(
        Project.id == project_id, Project.owner_id == owner_id, Project.deleted_at.is_(None)
    )
    if for_update:
        stmt = stmt.with_for_update()
    project = db.execute(stmt).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _lock_user_for_update(db: Session, user_id: uuid.UUID) -> User:
    return db.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectRead:
    project = Project(owner_id=current_user.id, name=payload.name)
    db.add(project)
    db.commit()
    return ProjectRead.model_validate(project)


@router.get("", response_model=list[ProjectRead])
def list_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ProjectRead]:
    projects = (
        db.execute(
            select(Project)
            .where(Project.owner_id == current_user.id, Project.deleted_at.is_(None))
            .order_by(Project.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [ProjectRead.model_validate(project) for project in projects]


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectRead:
    project = _get_owned_project(db, project_id, current_user.id)
    return ProjectRead.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProjectRead:
    project = _get_owned_project(db, project_id, current_user.id)
    project.name = payload.name
    db.commit()
    return ProjectRead.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: ObjectStorage = Depends(get_storage),
) -> None:
    # Lock order: User, then the target Project -- same discipline as the
    # uploads router. Locking the project row here also serializes against
    # a concurrent finalize/initiate for its video asset.
    _lock_user_for_update(db, current_user.id)
    project = _get_owned_project(db, project_id, current_user.id, for_update=True)

    # Cancel any active jobs so this project's deletion doesn't leave a
    # QUEUED/RUNNING job permanently blocking the owner's
    # active-job-count quota for future uploads elsewhere.
    active_analysis_jobs = (
        db.execute(
            select(AnalysisJob)
            .where(
                AnalysisJob.project_id == project.id,
                AnalysisJob.status.in_(list(ACTIVE_JOB_STATUSES)),
            )
            .with_for_update()
        )
        .scalars()
        .all()
    )
    for job in active_analysis_jobs:
        job.status = JobStatus.CANCELLED
        job.finished_at = utcnow()
        job.failure_summary = "Cancelled because the project was deleted"
        quota_service.record_ledger_event(
            db,
            user_id=current_user.id,
            event_type=QuotaLedgerEventType.ANALYSIS_CANCELLED,
            analysis_job_id=job.id,
        )

    active_export_jobs = (
        db.execute(
            select(ExportJob)
            .where(
                ExportJob.project_id == project.id,
                ExportJob.status.in_(list(ACTIVE_JOB_STATUSES)),
            )
            .with_for_update()
        )
        .scalars()
        .all()
    )
    for export_job in active_export_jobs:
        export_job.status = JobStatus.CANCELLED
        export_job.finished_at = utcnow()
        export_job.failure_summary = "Cancelled because the project was deleted"

    video_asset = project.video_asset
    if video_asset is not None:
        # Release any outstanding analysis/storage reservation
        # idempotently -- these helpers are no-ops if already released, so
        # this is safe even for an asset already cleanup_pending/aborted.
        # Counted (post-finalize actual) storage bytes are deliberately
        # NOT released here: they must stay charged until the queued
        # DELETE_OBJECT cleanup task actually succeeds, so a still-failing
        # delete doesn't stop being counted against quota.
        reservation_service.release_analysis_reservation(db, video_asset)
        reservation_service.release_storage_reservation(db, video_asset)

        task: StorageCleanupTask | None = None
        if video_asset.status == VideoAssetStatus.UPLOAD_INITIATED and video_asset.upload_id:
            # Never finished uploading: nothing was ever completed in
            # storage, so the cleanup action is aborting the multipart
            # upload rather than deleting a (nonexistent) object.
            video_asset.status = VideoAssetStatus.CLEANUP_PENDING
            task = storage_cleanup_service.get_or_create_cleanup_task(
                db,
                project_id=project.id,
                video_asset_id=video_asset.id,
                object_key=video_asset.object_key,
                upload_id=video_asset.upload_id,
                operation=StorageCleanupOperation.ABORT_MULTIPART,
            )
        elif video_asset.status in (
            VideoAssetStatus.FINALIZING,
            VideoAssetStatus.UPLOADED,
            VideoAssetStatus.CLEANUP_PENDING,
        ):
            # An object may already exist in storage (finalizing, uploaded,
            # or a prior cleanup still pending): queue its deletion.
            video_asset.status = VideoAssetStatus.CLEANUP_PENDING
            task = storage_cleanup_service.get_or_create_cleanup_task(
                db,
                project_id=project.id,
                video_asset_id=video_asset.id,
                object_key=video_asset.object_key,
                upload_id=None,
                operation=StorageCleanupOperation.DELETE_OBJECT,
            )
        # UPLOAD_ABORTED already has no outstanding storage-side artifact to
        # clean up -- nothing further to queue.

        project.deleted_at = utcnow()
        db.commit()

        if task is not None:
            storage_cleanup_service.claim_and_process(db, task.id, storage)
    else:
        project.deleted_at = utcnow()
        db.commit()
