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

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import get_current_user, get_storage
from app.models.base import ensure_aware, utcnow
from app.models.cleanup import StorageCleanupTask
from app.models.enums import (
    JobStatus,
    QuotaLedgerEventType,
    StorageCleanupOperation,
    StorageCleanupStatus,
    VideoAssetStatus,
)
from app.models.job import AnalysisJob
from app.models.project import Project
from app.models.quota import current_accounting_month
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
from app.services import reservations as reservation_service
from app.services import storage_cleanup as storage_cleanup_service
from app.services.storage import MultipartUploadNotFound, ObjectNotFound, ObjectStorage, UploadPart
from app.task_dispatch import enqueue_analysis_job

router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["uploads"])


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


def _get_owned_video_asset(
    db: Session,
    project: Project,
    video_asset_id: uuid.UUID,
    *,
    for_update: bool = False,
    populate_existing: bool = False,
) -> VideoAsset:
    stmt = select(VideoAsset).where(
        VideoAsset.id == video_asset_id, VideoAsset.project_id == project.id
    )
    if for_update:
        stmt = stmt.with_for_update()
    if populate_existing:
        # This row may already be present in this session's identity map
        # (e.g. from the lock taken at the top of this request), and a
        # concurrent commit from another session -- releasing this asset's
        # reservations as part of tombstoning its project -- must be
        # observed here rather than returning stale in-memory attributes.
        # Without this, a stale non-zero reservation would look releasable
        # again even though it was already released, double-releasing it.
        stmt = stmt.execution_options(populate_existing=True)
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


def _compute_part_lengths(size_bytes: int, part_count: int, min_part_size_bytes: int) -> list[int]:
    """Deterministic part sizing: parts ``1..part_count-1`` each get
    ``ceil(size_bytes / part_count)`` bytes, and the final part gets
    whatever remains.

    Raises ``ValueError`` (mapped by the caller to a 422) if the remainder
    is not a positive length -- a declared size too small for the
    requested part count can never be split into that many positive-length
    parts -- or if a non-final part would be smaller than
    ``min_part_size_bytes``. A single-part upload (``part_count == 1``) is
    always allowed regardless of size, since there is no non-final part to
    constrain and S3 has no minimum for the last/only part of an upload.
    """
    part_size = -(-size_bytes // part_count)  # ceil division
    final_part_size = size_bytes - part_size * (part_count - 1)
    if final_part_size <= 0:
        raise ValueError(
            f"Declared size {size_bytes} cannot be split into {part_count} positive-length parts"
        )
    if part_count > 1 and part_size < min_part_size_bytes:
        raise ValueError(
            f"Non-final part size {part_size} is smaller than the "
            f"{min_part_size_bytes} byte minimum part size"
        )
    return [part_size] * (part_count - 1) + [final_part_size]


def _abort_and_queue_object_cleanup(
    db: Session,
    video_asset: VideoAsset,
    project: Project,
    storage: ObjectStorage,
) -> None:
    """Handle a finalize integrity failure discovered *after* the object was
    already completed in storage: release both outstanding reservations,
    mark the asset ``CLEANUP_PENDING``, and persist+commit a durable
    ``DELETE_OBJECT`` cleanup task *before* attempting deletion.

    The durable state (reservations released, cleanup task persisted) is
    committed first so a crash before or during the synchronous delete
    attempt below never leaves the object untracked -- the task simply
    stays ``pending``/``failed`` until something claims it again. Whether
    the synchronous delete below succeeds or not, the caller still returns
    the original validation error: cleanup success/failure does not change
    the fact that this upload is invalid.
    """
    reservation_service.release_analysis_reservation(db, video_asset)
    reservation_service.release_storage_reservation(db, video_asset)
    video_asset.status = VideoAssetStatus.CLEANUP_PENDING

    task = storage_cleanup_service.get_or_create_cleanup_task(
        db,
        project_id=project.id,
        video_asset_id=video_asset.id,
        object_key=video_asset.object_key,
        upload_id=None,
        operation=StorageCleanupOperation.DELETE_OBJECT,
        generation=video_asset.cleanup_generation,
    )
    db.commit()

    storage_cleanup_service.claim_and_process(db, task.id, storage)


@router.post("/uploads", response_model=UploadInitiateResponse, status_code=status.HTTP_201_CREATED)
def initiate_upload(
    project_id: uuid.UUID,
    payload: UploadInitiateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
    storage: ObjectStorage = Depends(get_storage),
) -> UploadInitiateResponse:
    # Lock order: User (for quota aggregates), then the active Project row,
    # held through multipart creation and VideoAsset persistence below. A
    # second concurrent initiate for the same project blocks on the project
    # lock until this transaction commits or rolls back, then re-reads
    # project.video_asset and observes this request's result rather than
    # racing it. The IntegrityError handling further down is a backstop for
    # any writer that does not follow this same locking discipline.
    locked_user = _lock_user_for_update(db, current_user.id)
    project = _get_owned_project(db, project_id, current_user.id, for_update=True)

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

    storage_limit = quota_service.storage_bytes_limit(locked_user, settings)
    storage_used_or_reserved = quota_service.storage_bytes_used(db, locked_user.id)
    if storage_used_or_reserved + payload.size_bytes > storage_limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Storage-bytes quota exceeded",
        )

    # Deterministic part sizing, validated before ever calling
    # create_multipart_upload: a declared size too small for the requested
    # part count, or a non-final part smaller than the configured minimum,
    # is rejected here rather than producing an unbounded/invalid part plan.
    try:
        part_lengths = _compute_part_lengths(
            payload.size_bytes, payload.part_count, settings.multipart_min_part_size_bytes
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    object_key = storage.generate_object_key(project_id=project.id, filename=payload.filename)
    upload_id = storage.create_multipart_upload(object_key=object_key, content_type=payload.content_type)

    upload_expires_at = utcnow() + timedelta(hours=settings.multipart_upload_ttl_hours)
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
        upload_expires_at=upload_expires_at,
    )
    db.add(video_asset)
    try:
        db.flush()
    except IntegrityError:
        # Lost a race against a concurrent initiate for this same project
        # that did not go through our project lock (e.g. a bug, or a test
        # simulating one). The external multipart upload we just created is
        # now orphaned unless we clean it up: best-effort abort it; if that
        # itself fails, persist a durable ABORT_MULTIPART cleanup task in a
        # fresh transaction so it is never left untracked.
        db.rollback()
        try:
            storage.abort_multipart_upload(object_key=object_key, upload_id=upload_id)
        except ClientError:
            task = StorageCleanupTask(
                project_id=project.id,
                object_key=object_key,
                upload_id=upload_id,
                operation=StorageCleanupOperation.ABORT_MULTIPART,
                status=StorageCleanupStatus.PENDING,
            )
            db.add(task)
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Project already has a video"
        ) from None

    part_urls = storage.generate_presigned_part_urls(
        object_key=object_key,
        upload_id=upload_id,
        part_lengths=part_lengths,
        expires_in_seconds=settings.presigned_url_ttl_seconds,
    )

    # Provisionally reserve monthly analysis-seconds and storage-bytes quota
    # against the client-declared duration/size. See QuotaLedgerEventType
    # for the full reservation/release/reconcile contract the finalize path
    # and the future worker must follow. Both reservations are stamped with
    # the current accounting month so a later release or worker resize
    # (which may happen after a calendar rollover) still targets the month
    # this reservation actually belongs to.
    reservation_month = current_accounting_month()
    video_asset.analysis_reserved_seconds = payload.duration_seconds
    video_asset.analysis_reservation_month = reservation_month
    video_asset.storage_reserved_bytes = payload.size_bytes
    video_asset.storage_reservation_month = reservation_month
    quota_service.record_ledger_event(
        db,
        user_id=current_user.id,
        event_type=QuotaLedgerEventType.ANALYSIS_RESERVED,
        video_asset_id=video_asset.id,
        seconds_delta=payload.duration_seconds,
        accounting_month=reservation_month,
    )
    quota_service.record_ledger_event(
        db,
        user_id=current_user.id,
        event_type=QuotaLedgerEventType.STORAGE_RESERVED,
        video_asset_id=video_asset.id,
        bytes_delta=payload.size_bytes,
        accounting_month=reservation_month,
    )

    # Schedule a durable ABORT_MULTIPART cleanup task for this upload's
    # expiry, so an abandoned multipart upload is eventually reclaimed by
    # run_due_storage_cleanup_sweep even if the client never finalizes or
    # deletes the project. Cancelled by finalize_upload once this exact
    # upload durably claims FINALIZING (see cancel_scheduled_task below).
    storage_cleanup_service.get_or_create_cleanup_task(
        db,
        project_id=project.id,
        video_asset_id=video_asset.id,
        object_key=object_key,
        upload_id=upload_id,
        operation=StorageCleanupOperation.ABORT_MULTIPART,
        generation=video_asset.cleanup_generation,
        not_before=upload_expires_at,
    )

    db.commit()

    return UploadInitiateResponse(
        video_asset_id=video_asset.id,
        object_key=object_key,
        upload_id=upload_id,
        part_urls=[
            PartUploadUrl(part_number=n, url=url, content_length_bytes=length)
            for n, url, length in part_urls
        ],
        expires_in_seconds=settings.presigned_url_ttl_seconds,
    )


def _load_finalize_response(db: Session, video_asset: VideoAsset) -> FinalizeUploadResponse:
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
    # Lock order: User, then Project, then the target VideoAsset -- same
    # discipline as initiate_upload. A second concurrent finalize call for
    # the same asset blocks here until this transaction (or, for a fresh
    # finalize, the durable FINALIZING claim below) commits, then re-reads
    # the row and observes the resulting terminal/claimed state.
    locked_user = _lock_user_for_update(db, current_user.id)
    project = _get_owned_project(db, project_id, current_user.id, for_update=True)
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
        return _load_finalize_response(db, video_asset)

    if video_asset.status in (VideoAssetStatus.UPLOAD_ABORTED, VideoAssetStatus.CLEANUP_PENDING):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Upload was aborted")

    if video_asset.status == VideoAssetStatus.FINALIZING:
        same_request = (
            video_asset.finalize_idempotency_key == payload.idempotency_key
            and video_asset.finalize_request_fingerprint == fingerprint
        )
        if not same_request:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Upload finalize already in progress with a different "
                    "idempotency key or payload"
                ),
            )
        # Same recorded request replaying after a crash/timeout between the
        # earlier commit below and the S3 completion call: resume without
        # redoing structural validation or re-persisting the claim.
    else:
        expected_part_numbers = set(range(1, video_asset.part_count + 1))
        requested_part_numbers = {part.part_number for part in payload.parts}
        if (
            len(payload.parts) != video_asset.part_count
            or requested_part_numbers != expected_part_numbers
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"Finalize must include exactly one entry per part number 1.."
                    f"{video_asset.part_count}, with no duplicates or gaps"
                ),
            )

        active_jobs = quota_service.active_analysis_job_count(db, locked_user.id)
        if active_jobs >= quota_service.max_active_analysis_jobs(locked_user, settings):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Active analysis job quota exceeded"
            )

        # Crash-safe finalize claim: persist FINALIZING plus the idempotency
        # key and request fingerprint, and COMMIT before ever calling S3. If
        # the process crashes right after S3 accepts CompleteMultipartUpload
        # but before this process observes success, this durable claim is
        # what lets a replay with the same key/fingerprint recover safely
        # instead of either double-completing or losing track of the object.
        video_asset.status = VideoAssetStatus.FINALIZING
        video_asset.finalize_idempotency_key = payload.idempotency_key
        video_asset.finalize_request_fingerprint = fingerprint

        # This exact upload request has now durably claimed FINALIZING, so
        # the scheduled multipart-expiry ABORT_MULTIPART task can never be
        # allowed to abort it: cancel it in the same transaction as the
        # claim commit below.
        storage_cleanup_service.cancel_scheduled_task(
            db, video_asset_id=video_asset.id, operation=StorageCleanupOperation.ABORT_MULTIPART
        )

    # Release the locks held above before the (potentially slow) S3 call:
    # nothing else in this request needs them until the completion phase
    # re-locks below.
    db.commit()

    try:
        storage.complete_multipart_upload(
            object_key=video_asset.object_key,
            upload_id=video_asset.upload_id,
            parts=[UploadPart(part_number=part.part_number, etag=part.etag) for part in payload.parts],
        )
    except MultipartUploadNotFound:
        # Recoverable only because a durable FINALIZING claim for this
        # exact key/fingerprint is guaranteed to already be committed by
        # both branches above: verify via head_object instead of trusting
        # NoSuchUpload as success.
        try:
            metadata = storage.head_object(object_key=video_asset.object_key)
        except ObjectNotFound:
            # Genuinely missing -- not the ambiguous "crashed after S3
            # accepted completion" case: the object never actually got
            # completed in storage. Re-lock, revalidate the claim, and
            # release outstanding reservations instead of leaving the
            # asset stuck in FINALIZING forever.
            locked_user = _lock_user_for_update(db, current_user.id)
            video_asset = _get_owned_video_asset(
                db, project, video_asset_id, for_update=True, populate_existing=True
            )
            claim_matches = (
                video_asset.finalize_idempotency_key == payload.idempotency_key
                and video_asset.finalize_request_fingerprint == fingerprint
            )
            if video_asset.status == VideoAssetStatus.FINALIZING and claim_matches:
                reservation_service.release_analysis_reservation(db, video_asset)
                reservation_service.release_storage_reservation(db, video_asset)
                video_asset.status = VideoAssetStatus.UPLOAD_ABORTED
                db.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Multipart upload was not found and no object was completed; "
                    "the upload must be retried"
                ),
            ) from None
    else:
        metadata = storage.head_object(object_key=video_asset.object_key)

    # Re-lock User, then the active Project (excluding a tombstone), then
    # the VideoAsset for the completion phase, and re-validate the claim is
    # still exactly this request's before mutating anything: the S3 call
    # above ran without holding any row locks, so a concurrent project
    # delete may have tombstoned the project (and released reservations)
    # while it was in flight.
    locked_user = _lock_user_for_update(db, current_user.id)
    # populate_existing=True: this project row may already be present in
    # this session's identity map from the lock taken at the top of this
    # request, and a concurrent delete committed by another session must
    # be observed here rather than returning stale in-memory attributes.
    current_project = db.execute(
        select(Project)
        .where(Project.id == project.id, Project.owner_id == current_user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    video_asset = _get_owned_video_asset(
        db, project, video_asset_id, for_update=True, populate_existing=True
    )

    if current_project is None or current_project.deleted_at is not None:
        # The project was tombstoned by a concurrent delete while this
        # call's S3 completion was in flight. head_object above already
        # confirmed the object now exists in storage -- possibly *after*
        # the delete's own cleanup task already ran to completion against
        # a not-yet-existent object -- so a fresh durable DELETE_OBJECT
        # cleanup task is required rather than assuming an earlier one
        # still covers it. Never create a job or report UPLOADED for a
        # tombstoned project.
        reservation_service.release_analysis_reservation(db, video_asset)
        reservation_service.release_storage_reservation(db, video_asset)
        video_asset.status = VideoAssetStatus.CLEANUP_PENDING
        # This object was only just confirmed to exist (head_object above,
        # after our own S3 completion call) -- strictly newer than any
        # cleanup attempt scheduled before that call returned. Bump the
        # asset's generation before creating the task so an earlier
        # same-generation DELETE_OBJECT task that might still be RUNNING
        # (its external delete already ran, against a not-yet-existent
        # object, but its completion commit has not landed yet) is never
        # reused: this guarantees a genuinely new successor task actually
        # attempts deletion of the object that exists now.
        video_asset.cleanup_generation += 1
        task = storage_cleanup_service.get_or_create_cleanup_task(
            db,
            project_id=video_asset.project_id,
            video_asset_id=video_asset.id,
            object_key=video_asset.object_key,
            upload_id=None,
            operation=StorageCleanupOperation.DELETE_OBJECT,
            generation=video_asset.cleanup_generation,
        )
        db.commit()
        storage_cleanup_service.claim_and_process(db, task.id, storage)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project was deleted")

    claim_matches = (
        video_asset.finalize_idempotency_key == payload.idempotency_key
        and video_asset.finalize_request_fingerprint == fingerprint
    )
    if video_asset.status == VideoAssetStatus.UPLOADED and claim_matches:
        return _load_finalize_response(db, video_asset)
    if video_asset.status != VideoAssetStatus.FINALIZING or not claim_matches:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Upload finalize claim was superseded by a concurrent request",
        )

    if metadata.size_bytes != video_asset.declared_size_bytes:
        _abort_and_queue_object_cleanup(db, video_asset, project, storage)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Uploaded object size does not match the declared size",
        )
    if metadata.size_bytes > settings.max_upload_size_bytes:
        _abort_and_queue_object_cleanup(db, video_asset, project, storage)
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Uploaded object exceeds the upload cap",
        )
    if metadata.content_type != video_asset.content_type:
        _abort_and_queue_object_cleanup(db, video_asset, project, storage)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Uploaded object content type does not match the declared content type",
        )

    active_jobs = quota_service.active_analysis_job_count(db, locked_user.id)
    if active_jobs >= quota_service.max_active_analysis_jobs(locked_user, settings):
        # The active-job slot filled up during the S3 call window. The
        # object already exists in storage at this point (the call above
        # succeeded), so this must go through the same durable
        # DELETE_OBJECT cleanup path as any other post-completion integrity
        # failure -- a bare release-and-abort here would leave the
        # just-completed object orphaned.
        _abort_and_queue_object_cleanup(db, video_asset, project, storage)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Active analysis job quota exceeded"
        )

    video_asset.actual_size_bytes = metadata.size_bytes
    video_asset.status = VideoAssetStatus.UPLOADED
    video_asset.retention_expires_at = utcnow() + timedelta(days=settings.asset_retention_days)

    # Reconcile the provisional storage-byte reservation to the actual
    # counted size: release the reservation and count the real size instead
    # of double-counting reservation + actual.
    reservation_service.release_storage_reservation(db, video_asset)
    video_asset.storage_counted_bytes = metadata.size_bytes

    # DB-level unique constraint on video_asset_id backstops this against
    # ever creating a second job for the same asset even if this idempotency
    # check somehow raced.
    job = AnalysisJob(
        project_id=project.id,
        video_asset_id=video_asset.id,
        owner_id=current_user.id,
        status=JobStatus.QUEUED,
        accounting_month=video_asset.analysis_reservation_month,
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

    if settings.task_dispatch_enabled:
        enqueue_analysis_job(job.id)

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
    if video_asset.retention_expires_at is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not available")
    remaining_seconds = int(
        (ensure_aware(video_asset.retention_expires_at) - utcnow()).total_seconds()
    )
    if remaining_seconds <= 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video has expired")
    expires_in_seconds = min(settings.presigned_url_ttl_seconds, remaining_seconds)

    url = storage.generate_presigned_get_url(
        object_key=video_asset.preview_object_key or video_asset.object_key,
        expires_in_seconds=expires_in_seconds,
    )
    return SignedUrlResponse(url=url, expires_in_seconds=expires_in_seconds)
