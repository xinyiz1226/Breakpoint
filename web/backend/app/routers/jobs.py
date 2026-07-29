from __future__ import annotations

import uuid

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db, get_session_factory
from app.deps import get_current_user, get_storage, get_stream_session_factory
from app.models.base import ensure_aware, utcnow
from app.models.enums import (
    ACTIVE_JOB_STATUSES,
    JobStatus,
    QuotaLedgerEventType,
    VideoAssetStatus,
    VideoDurationStatus,
)
from app.models.job import AnalysisJob, ExportJob
from app.models.project import Project
from app.models.rally import Rally, RallyEdit
from app.models.user import User
from app.models.video import VideoAsset
from app.schemas.job import AnalysisJobRead, ExportJobRead
from app.schemas.rally import RallyEditRead, RallyEditUpdate, RallyRead
from app.services import reservations as reservation_service
from app.services import quota as quota_service
from app.services.job_events import iter_job_events
from app.services.storage import ObjectStorage
from app.task_dispatch import enqueue_export_job
from app.schemas.video import SignedUrlResponse
from app.security import decode_access_token

router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["jobs"])
_stream_bearer = HTTPBearer(auto_error=False)


def _stream_owner_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_stream_bearer),
    settings: Settings = Depends(get_settings),
    session_factory=Depends(get_stream_session_factory),
) -> uuid.UUID:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_access_token(
            credentials.credentials,
            secret_key=settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        owner_id = uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    with session_factory() as db:
        user = db.get(User, owner_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Account not available")
    return owner_id


def _project(db: Session, project_id: uuid.UUID, owner_id: uuid.UUID) -> Project:
    project = db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.owner_id == owner_id,
            Project.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _lock_project(db: Session, project_id: uuid.UUID, owner_id: uuid.UUID) -> Project:
    project = db.execute(
        select(Project)
        .where(
            Project.id == project_id,
            Project.owner_id == owner_id,
            Project.deleted_at.is_(None),
        )
        .with_for_update()
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _analysis_job(
    db: Session,
    project_id: uuid.UUID,
    owner_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> AnalysisJob:
    stmt = (
        select(AnalysisJob)
        .where(
            AnalysisJob.project_id == project_id,
            AnalysisJob.owner_id == owner_id,
        )
        .order_by(AnalysisJob.created_at.desc())
    )
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    job = db.execute(stmt).scalars().first()
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")
    return job


def _lock_live_export_source(
    db: Session, project_id: uuid.UUID, owner_id: uuid.UUID
) -> VideoAsset:
    asset = db.execute(
        select(VideoAsset)
        .where(
            VideoAsset.project_id == project_id,
            VideoAsset.owner_id == owner_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if (
        asset is None
        or asset.status != VideoAssetStatus.UPLOADED
        or not asset.object_key
        or asset.retention_expires_at is None
        or ensure_aware(asset.retention_expires_at) <= ensure_aware(utcnow())
    ):
        raise HTTPException(
            status_code=409, detail="Source video is unavailable or expired"
        )
    return asset


def _require_no_active_export(
    db: Session, project_id: uuid.UUID, *, excluding: uuid.UUID | None = None
) -> None:
    stmt = select(ExportJob.id).where(
        ExportJob.project_id == project_id,
        ExportJob.status.in_(list(ACTIVE_JOB_STATUSES)),
    )
    if excluding is not None:
        stmt = stmt.where(ExportJob.id != excluding)
    if db.execute(stmt).first() is not None:
        raise HTTPException(status_code=409, detail="An export is already active")


@router.get("/analysis", response_model=AnalysisJobRead)
def get_analysis(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnalysisJob:
    _project(db, project_id, current_user.id)
    return _analysis_job(db, project_id, current_user.id)


@router.post("/analysis/cancel", response_model=AnalysisJobRead)
def cancel_analysis(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnalysisJob:
    db.execute(select(User).where(User.id == current_user.id).with_for_update()).scalar_one()
    _lock_project(db, project_id, current_user.id)
    job = _analysis_job(db, project_id, current_user.id, for_update=True)
    if job.status == JobStatus.QUEUED:
        asset = job.video_asset
        reservation_service.release_analysis_reservation(db, asset)
        quota_service.record_ledger_event(
            db,
            user_id=current_user.id,
            event_type=QuotaLedgerEventType.ANALYSIS_CANCELLED,
            analysis_job_id=job.id,
            video_asset_id=asset.id,
        )
        job.status = JobStatus.CANCELLED
        job.lease_token = uuid.uuid4()
        job.failure_summary = "Analysis cancelled"
        job.finished_at = utcnow()
    elif job.status == JobStatus.RUNNING and job.cancel_requested_at is None:
        job.cancel_requested_at = utcnow()
    job.event_version += 1
    db.commit()
    return job


@router.post("/analysis/retry", response_model=AnalysisJobRead)
def retry_analysis(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> AnalysisJob:
    user = db.execute(
        select(User).where(User.id == current_user.id).with_for_update()
    ).scalar_one()
    _lock_project(db, project_id, current_user.id)
    job = _analysis_job(db, project_id, current_user.id, for_update=True)
    if job.status != JobStatus.FAILED:
        raise HTTPException(status_code=409, detail="Only failed analysis jobs can be retried")
    asset = db.execute(
        select(VideoAsset).where(VideoAsset.id == job.video_asset_id).with_for_update()
    ).scalar_one()
    if asset.duration_status == VideoDurationStatus.EXCEEDED:
        raise HTTPException(status_code=409, detail="Video exceeds the duration cap")
    reserve_seconds = float(asset.duration_seconds or asset.declared_duration_seconds)
    accounting_month = job.accounting_month
    used = quota_service.monthly_analysis_seconds_used(
        db, current_user.id, accounting_month=accounting_month
    )
    if used + reserve_seconds > quota_service.monthly_analysis_seconds_limit(user, settings):
        raise HTTPException(status_code=403, detail="Monthly analysis-seconds quota exceeded")
    quota_service.record_ledger_event(
        db,
        user_id=current_user.id,
        event_type=QuotaLedgerEventType.ANALYSIS_RESERVED,
        video_asset_id=asset.id,
        seconds_delta=reserve_seconds,
        accounting_month=accounting_month,
    )
    asset.analysis_reserved_seconds = reserve_seconds
    asset.analysis_reservation_month = accounting_month
    job.status = JobStatus.QUEUED
    job.lease_token = None
    job.heartbeat_at = None
    job.cancel_requested_at = None
    job.failure_summary = None
    job.failure_detail = None
    job.finished_at = None
    job.event_version += 1
    db.commit()
    if settings.task_dispatch_enabled:
        from app.task_dispatch import enqueue_analysis_job

        enqueue_analysis_job(job.id)
    return job


@router.get("/analysis/events")
def analysis_events(
    project_id: uuid.UUID,
    last_event_id_header: str | None = Header(None, alias="Last-Event-ID"),
    owner_id: uuid.UUID = Depends(_stream_owner_id),
    session_factory=Depends(get_stream_session_factory),
) -> StreamingResponse:
    factory = session_factory
    with factory() as db:
        _project(db, project_id, owner_id)
        job_id = _analysis_job(db, project_id, owner_id).id
    last_event_id = int(last_event_id_header) if last_event_id_header is not None else -1
    return StreamingResponse(
        iter_job_events(
            factory,
            job_kind="analysis",
            job_id=job_id,
            owner_id=owner_id,
            last_event_id=last_event_id,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/rallies", response_model=list[RallyRead])
def list_rallies(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Rally]:
    _project(db, project_id, current_user.id)
    job = _analysis_job(db, project_id, current_user.id)
    return list(
        db.execute(
            select(Rally)
            .where(Rally.analysis_job_id == job.id)
            .order_by(Rally.source_index)
        ).scalars()
    )


@router.patch("/rallies/{rally_id}", response_model=RallyEditRead)
def update_rally(
    project_id: uuid.UUID,
    rally_id: uuid.UUID,
    payload: RallyEditUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RallyEdit:
    _project(db, project_id, current_user.id)
    rally = db.execute(
        select(Rally)
        .join(AnalysisJob, Rally.analysis_job_id == AnalysisJob.id)
        .where(
            Rally.id == rally_id,
            AnalysisJob.project_id == project_id,
            AnalysisJob.owner_id == current_user.id,
        )
    ).scalar_one_or_none()
    if rally is None:
        raise HTTPException(status_code=404, detail="Rally not found")
    start = payload.adjusted_start if payload.adjusted_start is not None else rally.start
    end = payload.adjusted_end if payload.adjusted_end is not None else rally.end
    if start < rally.start or end > rally.end or end <= start:
        raise HTTPException(status_code=422, detail="Adjusted range must stay within the rally")
    rally.edit.included = payload.included
    rally.edit.adjusted_start = payload.adjusted_start
    rally.edit.adjusted_end = payload.adjusted_end
    db.commit()
    return rally.edit


@router.post("/exports", response_model=ExportJobRead, status_code=status.HTTP_201_CREATED)
def create_export(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> ExportJob:
    db.execute(
        select(User).where(User.id == current_user.id).with_for_update()
    ).scalar_one()
    _lock_project(db, project_id, current_user.id)
    _lock_live_export_source(db, project_id, current_user.id)
    _require_no_active_export(db, project_id)
    analysis = _analysis_job(db, project_id, current_user.id)
    if analysis.status != JobStatus.SUCCEEDED:
        raise HTTPException(status_code=409, detail="Analysis must succeed before export")
    rallies = db.execute(
        select(Rally)
        .where(Rally.analysis_job_id == analysis.id)
        .order_by(Rally.source_index)
    ).scalars().all()
    snapshot = [
        {
            "rally_id": str(rally.id),
            "start": rally.edit.adjusted_start
            if rally.edit.adjusted_start is not None
            else rally.start,
            "end": rally.edit.adjusted_end
            if rally.edit.adjusted_end is not None
            else rally.end,
        }
        for rally in rallies
        if rally.edit.included
    ]
    if not snapshot:
        raise HTTPException(status_code=422, detail="Select at least one rally")
    job = ExportJob(
        project_id=project_id,
        owner_id=current_user.id,
        status=JobStatus.QUEUED,
        selection_snapshot=snapshot,
        event_version=1,
    )
    db.add(job)
    db.commit()
    if settings.task_dispatch_enabled:
        enqueue_export_job(job.id)
    return job


@router.get("/exports/{export_job_id}", response_model=ExportJobRead)
def get_export(
    project_id: uuid.UUID,
    export_job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExportJob:
    _project(db, project_id, current_user.id)
    job = db.execute(
        select(ExportJob).where(
            ExportJob.id == export_job_id,
            ExportJob.project_id == project_id,
            ExportJob.owner_id == current_user.id,
        )
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Export job not found")
    return job


def _export_job(
    db: Session,
    project_id: uuid.UUID,
    export_job_id: uuid.UUID,
    owner_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> ExportJob:
    stmt = select(ExportJob).where(
            ExportJob.id == export_job_id,
            ExportJob.project_id == project_id,
            ExportJob.owner_id == owner_id,
        )
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    job = db.execute(stmt).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Export job not found")
    return job


@router.post("/exports/{export_job_id}/cancel", response_model=ExportJobRead)
def cancel_export(
    project_id: uuid.UUID,
    export_job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExportJob:
    db.execute(
        select(User).where(User.id == current_user.id).with_for_update()
    ).scalar_one()
    _lock_project(db, project_id, current_user.id)
    job = _export_job(
        db,
        project_id,
        export_job_id,
        current_user.id,
        for_update=True,
    )
    if job.status == JobStatus.QUEUED:
        job.status = JobStatus.CANCELLED
        job.lease_token = uuid.uuid4()
        job.failure_summary = "Export cancelled"
        job.finished_at = utcnow()
    elif job.status == JobStatus.RUNNING and job.cancel_requested_at is None:
        job.cancel_requested_at = utcnow()
    job.event_version += 1
    db.commit()
    return job


@router.post("/exports/{export_job_id}/retry", response_model=ExportJobRead)
def retry_export(
    project_id: uuid.UUID,
    export_job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> ExportJob:
    db.execute(
        select(User).where(User.id == current_user.id).with_for_update()
    ).scalar_one()
    _lock_project(db, project_id, current_user.id)
    _lock_live_export_source(db, project_id, current_user.id)
    _require_no_active_export(db, project_id, excluding=export_job_id)
    job = db.execute(
        select(ExportJob)
        .where(
            ExportJob.id == export_job_id,
            ExportJob.project_id == project_id,
            ExportJob.owner_id == current_user.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Export job not found")
    if job.status != JobStatus.FAILED:
        raise HTTPException(status_code=409, detail="Only failed export jobs can be retried")
    job.status = JobStatus.QUEUED
    job.lease_token = None
    job.heartbeat_at = None
    job.cancel_requested_at = None
    job.failure_summary = None
    job.failure_detail = None
    job.finished_at = None
    job.event_version += 1
    db.commit()
    if settings.task_dispatch_enabled:
        enqueue_export_job(job.id)
    return job


@router.get("/exports/{export_job_id}/events")
def export_events(
    project_id: uuid.UUID,
    export_job_id: uuid.UUID,
    last_event_id_header: str | None = Header(None, alias="Last-Event-ID"),
    owner_id: uuid.UUID = Depends(_stream_owner_id),
    session_factory=Depends(get_stream_session_factory),
) -> StreamingResponse:
    factory = session_factory
    with factory() as db:
        _project(db, project_id, owner_id)
        job_id = _export_job(db, project_id, export_job_id, owner_id).id
    return StreamingResponse(
        iter_job_events(
            factory,
            job_kind="export",
            job_id=job_id,
            owner_id=owner_id,
            last_event_id=(
                int(last_event_id_header)
                if last_event_id_header is not None
                else -1
            ),
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/exports/{export_job_id}/signed-url", response_model=SignedUrlResponse)
def export_signed_url(
    project_id: uuid.UUID,
    export_job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    storage: ObjectStorage = Depends(get_storage),
) -> SignedUrlResponse:
    _project(db, project_id, current_user.id)
    job = _export_job(db, project_id, export_job_id, current_user.id)
    if job.status != JobStatus.SUCCEEDED or job.output_object_key is None:
        raise HTTPException(status_code=404, detail="Export is not available")
    if job.output_expires_at is None:
        raise HTTPException(status_code=404, detail="Export is not available")
    remaining_seconds = int(
        (ensure_aware(job.output_expires_at) - utcnow()).total_seconds()
    )
    if remaining_seconds <= 0:
        raise HTTPException(status_code=404, detail="Export has expired")
    expires_in_seconds = min(
        settings.presigned_url_ttl_seconds, remaining_seconds
    )
    return SignedUrlResponse(
        url=storage.generate_presigned_get_url(
            object_key=job.output_object_key,
            expires_in_seconds=expires_in_seconds,
        ),
        expires_in_seconds=expires_in_seconds,
    )
