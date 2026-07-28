"""Durable storage-cleanup outbox processing.

Callers persist a ``StorageCleanupTask`` (and commit) *before* attempting
the corresponding S3 side effect, then immediately call
``claim_and_process`` for synchronous best-effort processing. If that fails
-- or the process crashes before ever calling it -- the task simply stays
``pending``/``failed`` until something claims and processes it again: either
another synchronous best-effort attempt at the next write to the same
asset, or an explicit sweep via ``retry_pending_cleanup_tasks`` (the
worker/ops seam this module exposes for that purpose -- no scheduler or
Celery is introduced here; something has to actually call it).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from botocore.exceptions import ClientError

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.cleanup import StorageCleanupTask
from app.models.enums import StorageCleanupOperation, StorageCleanupStatus, VideoAssetStatus
from app.models.user import User
from app.models.video import VideoAsset
from app.services import reservations as reservation_service
from app.services.storage import ObjectStorage


def get_or_create_cleanup_task(
    db: Session,
    *,
    project_id: uuid.UUID | None,
    video_asset_id: uuid.UUID | None,
    object_key: str,
    upload_id: str | None,
    operation: StorageCleanupOperation,
) -> StorageCleanupTask:
    """Idempotency helper: reuse an already-unfinished (pending/running/
    failed) cleanup task for the same video asset + operation instead of
    enqueuing a duplicate.

    A new task is only created if no such unfinished task currently
    exists -- including the case where an earlier task for this asset
    already ran to ``COMPLETED`` (e.g. it deleted a not-yet-existent
    object during a finalize/delete race) and a freshly-completed storage
    object now needs its own cleanup. Callers that persist a task via this
    helper must still ``db.commit()`` before attempting the corresponding
    storage side effect, same as constructing one directly.
    """
    if video_asset_id is not None:
        existing = db.execute(
            select(StorageCleanupTask)
            .where(
                StorageCleanupTask.video_asset_id == video_asset_id,
                StorageCleanupTask.operation == operation,
                StorageCleanupTask.status.in_(
                    (
                        StorageCleanupStatus.PENDING,
                        StorageCleanupStatus.RUNNING,
                        StorageCleanupStatus.FAILED,
                    )
                ),
            )
            .with_for_update()
        ).scalars().first()
        if existing is not None:
            return existing

    task = StorageCleanupTask(
        project_id=project_id,
        video_asset_id=video_asset_id,
        object_key=object_key,
        upload_id=upload_id,
        operation=operation,
        status=StorageCleanupStatus.PENDING,
    )
    db.add(task)
    return task


def claim_and_process(db: Session, task: StorageCleanupTask, storage: ObjectStorage) -> None:
    """Idempotently perform the durable operation described by ``task``.

    Safe to call more than once for the same task: an already-``COMPLETED``
    task is a no-op, and both ``delete_object`` and
    ``abort_multipart_upload`` are themselves idempotent against a repeat
    call for an object/upload that is already gone.
    """
    if task.status == StorageCleanupStatus.COMPLETED:
        return

    task.status = StorageCleanupStatus.RUNNING
    task.claimed_at = utcnow()
    task.attempts += 1
    db.commit()

    try:
        if task.operation == StorageCleanupOperation.DELETE_OBJECT:
            storage.delete_object(object_key=task.object_key)
        else:
            assert task.upload_id is not None
            storage.abort_multipart_upload(object_key=task.object_key, upload_id=task.upload_id)
    except ClientError as exc:
        task.status = StorageCleanupStatus.FAILED
        task.last_error = str(exc)
        db.commit()
        return

    task.status = StorageCleanupStatus.COMPLETED
    task.completed_at = utcnow()

    if task.video_asset_id is not None:
        video_asset = db.get(VideoAsset, task.video_asset_id)
        if video_asset is not None:
            # Lock the owning User before mutating accounting fields, per
            # the User-first locking discipline used everywhere else that
            # writes ledger/reservation state.
            db.execute(
                select(User).where(User.id == video_asset.owner_id).with_for_update()
            ).scalar_one()
            # Only now that the storage-side delete has actually succeeded
            # is it safe to release previously *counted* stored bytes:
            # releasing them eagerly (e.g. at project-delete time, before
            # this ever runs) would let a still-failing delete stop being
            # charged for storage it still occupies.
            reservation_service.release_counted_storage_bytes(db, video_asset)
            if video_asset.status == VideoAssetStatus.CLEANUP_PENDING:
                # The durable cleanup this asset was waiting on is now
                # done; nothing is left to clean up, so it can move to the
                # same terminal state a directly-aborted upload reaches.
                video_asset.status = VideoAssetStatus.UPLOAD_ABORTED

    db.commit()


def retry_pending_cleanup_tasks(
    db: Session, storage: ObjectStorage, *, limit: int = 50, stale_after_seconds: int = 300
) -> int:
    """Explicit worker/ops seam: scan and retry outstanding cleanup tasks.

    Selects up to ``limit`` tasks (locking them with
    ``SELECT ... FOR UPDATE SKIP LOCKED`` where the backend supports it --
    e.g. Postgres; SQLite ignores the locking hint but still simply returns
    the matching rows) and processes each idempotently via
    ``claim_and_process``. Callable on demand by an operator, a management
    command, or a future worker process -- no scheduler/Celery is
    introduced by this function itself, but this is the real retry path:
    it actually scans for and retries outstanding work.

    Matches ``PENDING``/``FAILED`` tasks, plus ``RUNNING`` tasks whose
    ``claimed_at`` is missing or older than ``stale_after_seconds``: a
    worker that crashed after claiming a task (setting it ``RUNNING``) but
    before completing it would otherwise leave that task stuck forever,
    since delete/abort are idempotent against a real backend, safely
    retrying such a stale claim is recoverable even if the original
    attempt's external call actually already succeeded. A ``RUNNING`` task
    claimed more recently than the cutoff is left alone -- it may still be
    genuinely in flight elsewhere. Returns the number of tasks this sweep
    attempted.
    """
    stale_before = utcnow() - timedelta(seconds=stale_after_seconds)
    stmt = (
        select(StorageCleanupTask)
        .where(
            or_(
                StorageCleanupTask.status.in_(
                    (StorageCleanupStatus.PENDING, StorageCleanupStatus.FAILED)
                ),
                and_(
                    StorageCleanupTask.status == StorageCleanupStatus.RUNNING,
                    or_(
                        StorageCleanupTask.claimed_at.is_(None),
                        StorageCleanupTask.claimed_at < stale_before,
                    ),
                ),
            )
        )
        .order_by(StorageCleanupTask.created_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    tasks = db.execute(stmt).scalars().all()
    for task in tasks:
        claim_and_process(db, task, storage)
    return len(tasks)
