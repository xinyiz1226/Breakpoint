"""Upload session lifecycle: presigned multipart initiation, idempotent
finalize, and signed playback URLs.

The API server never touches video bytes. It only creates presigned S3 URLs
and records/validates metadata after the browser uploads directly to object
storage.

Duration handling: ``initiate_upload`` accepts and validates a
client-declared duration and provisionally reserves monthly analysis-seconds
quota against it (``QuotaLedgerEventType.ANALYSIS_RESERVED``). This is a
declaration, not a fact — the API never probes media. ``finalize_upload``
releases that reservation if its own (synchronous) integrity checks fail,
since the asset will never be analyzed. The remaining reservation lifecycle
(ffprobe-based validation and reconciliation to actual usage) belongs to the
future analysis worker; see ``QuotaLedgerEventType`` for the full contract.

Concurrency: both endpoints lock the caller's ``User`` row
(``SELECT ... FOR UPDATE``) before any quota aggregate check or ledger/job
write, so concurrent requests for the same user serialize around quota
enforcement instead of racing on stale counts. ``finalize_upload``
additionally locks the target ``VideoAsset`` row for its entire transaction,
so a concurrent retry of the same finalize call waits for the first to
commit and then observes the already-``UPLOADED`` terminal state via the
idempotency check, rather than double-completing the multipart upload or
double-creating the analysis job.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import get_current_user, get_storage
from app.models.base import utcnow
from app.models.enums import JobStatus, QuotaLedgerEventType, VideoAssetStatus
from app.models.job import AnalysisJob
from app.models.project import Project
from app.models.user import User
from app.models.video import VideoAsset
from app.schemas.job import AnalysisJobRead
from app.schemas.video import (
    ALLOWED_VIDEO_CONTENT_TYPES,
    FinalizeUploadRequest,
    FinalizeUploadResponse,
    PartUploadUrl,
    SignedUrlResponse,
    UploadInitiateRequest,
    UploadInitiateResponse,
    VideoAssetRead,
)
from app.services import quota as quota_service
from app.services.storage import ObjectStorage, UploadPart

router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["uploads"])


def _get_owned_project(db: Session, project_id: uuid.UUID, owner_id: uuid.UUID) -> Project:
    project = db.execute(
        select(Project).where(Project.id == project_id, Project.owner_id == owner_id)
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _get_owned_video_asset(
    db: Session, project: Project, video_asset_id: uuid.UUID, *, for_update: bool = False
) -> VideoAsset:
    stmt = select(VideoAsset).where(
        VideoAsset.id == video_asset_id, VideoAsset.project_id == project.id
    )
    if for_update:
        stmt = stmt.with_for_update()
    video_asset = db.execute(stmt).scalar_one_or_none()
    if video_asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video asset not found")
    return video_asset


def _lock_user_for_update(db: Session, user_id: uuid.UUID) -> User:
    """Lock the caller's user row so quota checks and their ledger/job
    writes serialize per-user.

    The user row is the natural serialization point for every quota limit
    enforced in this module (active job count, monthly reserved-or-used
    seconds): locking it here means a second concurrent request for the
    same user blocks until the first request's transaction commits, so it
    always reads post-commit numbers rather than racing against a
    still-in-flight reservation or job creation.
    """
    return db.execute(select(User).where(User.id == user_id).with_for_update()).scalar_one()


def _fingerprint_parts(parts: list[dict[str, object]]) -> str:
    ordered = sorted(parts, key=lambda part: part["part_number"])
    canonical = json.dumps(ordered, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _abort_upload_and_release_reservation(
    db: Session, video_asset: VideoAsset, owner_id: uuid.UUID
) -> None:
    """Mark the asset aborted and release its provisional quota reservation.

    Called when finalize's post-complete integrity checks fail: the asset
    will never be analyzed, so the ANALYSIS_RESERVED entry made at initiate
    must be released rather than permanently consuming the user's monthly
    quota for a video that was never usable.
    """
    video_asset.status = VideoAssetStatus.UPLOAD_ABORTED
    quota_service.record_ledger_event(
        db,
        user_id=owner_id,
        event_type=QuotaLedgerEventType.ANALYSIS_RESERVATION_RELEASED,
        video_asset_id=video_asset.id,
        seconds_delta=-video_asset.declared_duration_seconds,
    )
    db.commit()


@router.post("/uploads", response_model=UploadInitiateResponse, status_code=status.HTTP_201_CREATED)
def initiate_upload(
    project_id: uuid.UUID,
    payload: UploadInitiateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    storage: ObjectStorage = Depends(get_storage),
) -> UploadInitiateResponse:
    project = _get_owned_project(db, project_id, current_user.id)

    if project.video_asset is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Project already has a video"
        )
    if payload.content_type not in ALLOWED_VIDEO_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type: {payload.content_type}",
        )
    if payload.size_bytes > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Declared size exceeds the {settings.max_upload_size_bytes} byte upload cap",
        )
    if payload.duration_seconds > settings.max_video_duration_seconds:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Declared duration exceeds the {settings.max_video_duration_seconds} "
                "second video duration cap"
            ),
        )

    # Lock the user row before any quota aggregate check or write: this is
    # the serialization point that prevents two concurrent uploads (or an
    # upload racing a concurrent finalize) from both reading a
    # not-yet-updated active-job count or reserved-seconds total and both
    # passing checks that, together, would exceed the limit.
    locked_user = _lock_user_for_update(db, current_user.id)

    active_jobs = quota_service.active_analysis_job_count(db, locked_user.id)
    if active_jobs >= quota_service.max_active_analysis_jobs(locked_user, settings):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Active analysis job quota exceeded"
        )

    seconds_limit = quota_service.monthly_analysis_seconds_limit(locked_user, settings)
    seconds_reserved_or_used = quota_service.monthly_analysis_seconds_used(db, locked_user.id)
    if seconds_reserved_or_used + payload.duration_seconds > seconds_limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Monthly analysis-seconds quota exceeded",
        )

    object_key = storage.generate_object_key(project_id=project.id, filename=payload.filename)
    upload_id = storage.create_multipart_upload(object_key=object_key, content_type=payload.content_type)
    part_urls = storage.generate_presigned_part_urls(
        object_key=object_key,
        upload_id=upload_id,
        part_count=payload.part_count,
        expires_in_seconds=settings.presigned_url_ttl_seconds,
    )

    video_asset = VideoAsset(
        project_id=project.id,
        owner_id=current_user.id,
        object_key=object_key,
        original_filename=payload.filename,
        content_type=payload.content_type,
        declared_size_bytes=payload.size_bytes,
        declared_duration_seconds=payload.duration_seconds,
        status=VideoAssetStatus.UPLOAD_INITIATED,
        upload_id=upload_id,
        part_count=payload.part_count,
    )
    db.add(video_asset)
    db.flush()

    # Provisionally reserve monthly analysis-seconds quota against the
    # client-declared duration. See QuotaLedgerEventType for the full
    # reservation/release/reconcile contract the finalize path and the
    # future worker must follow.
    quota_service.record_ledger_event(
        db,
        user_id=current_user.id,
        event_type=QuotaLedgerEventType.ANALYSIS_RESERVED,
        video_asset_id=video_asset.id,
        seconds_delta=payload.duration_seconds,
    )
    db.commit()

    return UploadInitiateResponse(
        video_asset_id=video_asset.id,
        object_key=object_key,
        upload_id=upload_id,
        part_urls=[PartUploadUrl(part_number=n, url=url) for n, url in part_urls],
        expires_in_seconds=settings.presigned_url_ttl_seconds,
    )


@router.post(
    "/uploads/{video_asset_id}/finalize",
    response_model=FinalizeUploadResponse,
)
def finalize_upload(
    project_id: uuid.UUID,
    video_asset_id: uuid.UUID,
    payload: FinalizeUploadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    storage: ObjectStorage = Depends(get_storage),
) -> FinalizeUploadResponse:
    project = _get_owned_project(db, project_id, current_user.id)
    # Lock the video asset row for the whole finalize transaction: a second
    # concurrent finalize call for the same asset (same or different
    # payload) blocks here until this transaction commits, then re-reads
    # the row and observes the terminal UPLOADED/UPLOAD_ABORTED status
    # instead of racing this request's storage-completion + DB writes.
    video_asset = _get_owned_video_asset(db, project, video_asset_id, for_update=True)

    requested_parts = [{"part_number": part.part_number, "etag": part.etag} for part in payload.parts]
    fingerprint = _fingerprint_parts(requested_parts)

    if video_asset.status == VideoAssetStatus.UPLOADED:
        same_request = (
            video_asset.finalize_idempotency_key == payload.idempotency_key
            and video_asset.finalize_request_fingerprint == fingerprint
        )
        if not same_request:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Upload already finalized with a different idempotency key or payload",
            )
        job = db.execute(
            select(AnalysisJob)
            .where(AnalysisJob.video_asset_id == video_asset.id)
            .order_by(AnalysisJob.created_at.asc())
        ).scalars().first()
        if job is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Finalized video asset is missing its analysis job",
            )
        return FinalizeUploadResponse(
            video_asset=VideoAssetRead.model_validate(video_asset),
            analysis_job=AnalysisJobRead.model_validate(job),
        )

    if video_asset.status == VideoAssetStatus.UPLOAD_ABORTED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Upload was aborted")

    expected_part_numbers = set(range(1, video_asset.part_count + 1))
    requested_part_numbers = {part.part_number for part in payload.parts}
    if len(payload.parts) != video_asset.part_count or requested_part_numbers != expected_part_numbers:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Finalize must include exactly one entry per part number 1.."
                f"{video_asset.part_count}, with no duplicates or gaps"
            ),
        )

    # Lock the user row before the active-job aggregate check and the
    # ledger/job writes below, for the same reason as in initiate_upload.
    locked_user = _lock_user_for_update(db, current_user.id)

    active_jobs = quota_service.active_analysis_job_count(db, locked_user.id)
    if active_jobs >= quota_service.max_active_analysis_jobs(locked_user, settings):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Active analysis job quota exceeded"
        )

    storage.complete_multipart_upload(
        object_key=video_asset.object_key,
        upload_id=video_asset.upload_id,
        parts=[UploadPart(part_number=part.part_number, etag=part.etag) for part in payload.parts],
    )
    metadata = storage.head_object(object_key=video_asset.object_key)
    if metadata.size_bytes != video_asset.declared_size_bytes:
        _abort_upload_and_release_reservation(db, video_asset, current_user.id)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Uploaded object size does not match the declared size",
        )
    if metadata.size_bytes > settings.max_upload_size_bytes:
        _abort_upload_and_release_reservation(db, video_asset, current_user.id)
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Uploaded object exceeds the upload cap",
        )
    if metadata.content_type != video_asset.content_type:
        _abort_upload_and_release_reservation(db, video_asset, current_user.id)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Uploaded object content type does not match the declared content type",
        )

    video_asset.actual_size_bytes = metadata.size_bytes
    video_asset.status = VideoAssetStatus.UPLOADED
    video_asset.retention_expires_at = utcnow() + timedelta(days=settings.asset_retention_days)
    video_asset.finalize_idempotency_key = payload.idempotency_key
    video_asset.finalize_request_fingerprint = fingerprint

    job = AnalysisJob(
        project_id=project.id,
        video_asset_id=video_asset.id,
        owner_id=current_user.id,
        status=JobStatus.QUEUED,
    )
    db.add(job)
    db.flush()

    quota_service.record_ledger_event(
        db,
        user_id=current_user.id,
        event_type=QuotaLedgerEventType.UPLOAD_FINALIZED,
        video_asset_id=video_asset.id,
        bytes_delta=metadata.size_bytes,
    )
    quota_service.record_ledger_event(
        db,
        user_id=current_user.id,
        event_type=QuotaLedgerEventType.ANALYSIS_QUEUED,
        analysis_job_id=job.id,
        video_asset_id=video_asset.id,
    )

    db.commit()

    return FinalizeUploadResponse(
        video_asset=VideoAssetRead.model_validate(video_asset),
        analysis_job=AnalysisJobRead.model_validate(job),
    )


@router.get("/video/signed-url", response_model=SignedUrlResponse)
def get_signed_video_url(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    storage: ObjectStorage = Depends(get_storage),
) -> SignedUrlResponse:
    project = _get_owned_project(db, project_id, current_user.id)
    video_asset = project.video_asset
    if video_asset is None or video_asset.status != VideoAssetStatus.UPLOADED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not available")

    url = storage.generate_presigned_get_url(
        object_key=video_asset.object_key, expires_in_seconds=settings.presigned_url_ttl_seconds
    )
    return SignedUrlResponse(url=url, expires_in_seconds=settings.presigned_url_ttl_seconds)
