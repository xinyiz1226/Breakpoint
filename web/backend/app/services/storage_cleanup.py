"""Durable storage-cleanup outbox processing.

Callers persist a ``StorageCleanupTask`` (and commit) *before* attempting
the corresponding S3 side effect, then immediately call
``claim_and_process`` for synchronous best-effort processing. If that fails
-- or the process crashes before ever calling it -- the task simply stays
``pending``/``failed`` until something claims and processes it again: either
another synchronous best-effort attempt at the next write to the same
asset, or an explicit sweep via ``retry_pending_cleanup_tasks``/
``run_due_storage_cleanup_sweep`` (the worker/ops seam this module exposes
for that purpose -- no scheduler or Celery is introduced here; something has
to actually call it).

Claiming is a two-phase, lease-based protocol so two callers (a synchronous
attempt and a concurrent stale-recovery sweep, or two sweeps) can never both
believe they own the same task:

1. ``_claim_task_for_processing`` (a direct claim by id) or
   ``_claim_next_due_task`` (a sweep's single-row claim, re-evaluating
   eligibility fresh) reselects a task under ``SELECT ... FOR UPDATE``,
   mints a fresh ``lease_token``, sets it ``RUNNING``, and commits. A task
   already ``RUNNING`` under someone else's still-fresh lease is left alone
   unless staleness has already been verified (only ``_claim_next_due_task``
   does this, by construction of its own eligibility query).
2. The external side effect runs. For most tasks it runs with no lock held
   (``_run_lock_free_and_complete``); a ``video_asset_id``-bearing
   ``ABORT_MULTIPART`` task instead holds User->Asset->Task locks through
   the call (``_process_abort_multipart_with_asset``), so a concurrent
   finalize claim that needs the same asset is forced to race deterministically
   against this worker for those locks rather than both proceeding.
3. Completion re-locks the task by id *and* the exact lease token from
   step 1. If that lease has since been superseded (stolen by a
   stale-recovery reclaim, or cancelled by a finalize claim), no matching
   row is found and this is a no-op: the current lease holder -- not this
   stale attempt -- owns finishing the task and its accounting.

A sweep (``retry_pending_cleanup_tasks``) never snapshots many task ids up
front and then blindly processes each by id: it claims exactly one
currently-eligible row at a time via ``_claim_next_due_task``, re-evaluating
eligibility fresh at the moment of each claim, and repeats up to ``limit``.
This is what prevents it from ever stealing a task that another caller has
since (and legitimately) claimed with a fresh lease between the sweep
starting and reaching that task.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from botocore.exceptions import ClientError

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.base import ensure_aware, utcnow
from app.models.cleanup import StorageCleanupTask
from app.models.enums import (
    JobStatus,
    StorageCleanupOperation,
    StorageCleanupStatus,
    VideoAssetStatus,
)
from app.models.job import AnalysisJob
from app.models.project import Project
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
    generation: int = 0,
    not_before: datetime | None = None,
) -> StorageCleanupTask:
    """Idempotency helper: reuse an already-unfinished (pending/running/
    failed) cleanup task for the same video asset + operation + generation
    instead of enqueuing a duplicate.

    A new task is only created if no such unfinished task currently
    exists -- including the case where an earlier task for this asset
    already ran to ``COMPLETED`` (e.g. it deleted a not-yet-existent
    object during a finalize/delete race) and a freshly-completed storage
    object now needs its own cleanup. Callers that persist a task via this
    helper must still ``db.commit()`` before attempting the corresponding
    storage side effect, same as constructing one directly.

    ``generation`` scopes the reuse search alongside ``video_asset_id`` and
    ``operation``: it is normally the asset's current
    ``cleanup_generation`` (unchanged), so ordinary retries keep reusing
    the same task. A caller that has just incremented the asset's
    generation (because an earlier same-generation task might still be
    ``RUNNING`` against a now-stale view of the object) is guaranteed a
    genuinely new task row rather than a reuse of that earlier one.

    ``not_before`` is only applied when creating a brand-new task (e.g. a
    scheduled multipart-expiry abort); reusing an existing unfinished task
    keeps that task's own scheduling.
    """
    if video_asset_id is not None:
        existing = db.execute(
            select(StorageCleanupTask)
            .where(
                StorageCleanupTask.video_asset_id == video_asset_id,
                StorageCleanupTask.operation == operation,
                StorageCleanupTask.generation == generation,
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
        generation=generation,
        not_before=not_before,
    )
    db.add(task)
    return task


def cancel_scheduled_task(
    db: Session, *, video_asset_id: uuid.UUID, operation: StorageCleanupOperation
) -> None:
    """Cancel any outstanding (not yet completed/cancelled) durable cleanup
    task for this asset + operation.

    Used once finalize has durably claimed (or completed) an exact upload
    request, so the multipart-expiry sweep can never abort an in-progress
    or already-finished request out from under it. ``PENDING``/``FAILED``
    tasks are simply cancelled. A task already ``RUNNING`` under a sweep's
    lease is also cancelled *and* has its lease token rotated to a fresh,
    unknown value: this is what makes the worker's own in-flight
    continuation -- still holding the old lease -- observe the supersession
    (via its own lease re-check) before it ever calls S3, rather than racing
    ahead to abort a multipart upload this exact request just finished (or
    is about to finish) claiming.
    """
    task = db.execute(
        select(StorageCleanupTask)
        .where(
            StorageCleanupTask.video_asset_id == video_asset_id,
            StorageCleanupTask.operation == operation,
            StorageCleanupTask.status.in_(
                (
                    StorageCleanupStatus.PENDING,
                    StorageCleanupStatus.FAILED,
                    StorageCleanupStatus.RUNNING,
                )
            ),
        )
        .with_for_update()
    ).scalars().first()
    if task is not None:
        task.status = StorageCleanupStatus.CANCELLED
        task.lease_token = uuid.uuid4()


def _claim_task_for_processing(
    db: Session, task_id: uuid.UUID, *, force_reclaim: bool = False
) -> tuple[StorageCleanupTask, uuid.UUID] | None:
    """Atomically claim ``task_id`` under a fresh lease and commit.

    Returns ``(task, lease_token)`` on success, or ``None`` if there is
    nothing to claim: the task does not exist, is already terminal
    (``COMPLETED``/``CANCELLED``), or is ``RUNNING`` under someone else's
    still-fresh lease and ``force_reclaim`` was not requested.
    """
    task = db.execute(
        select(StorageCleanupTask).where(StorageCleanupTask.id == task_id).with_for_update()
    ).scalar_one_or_none()
    if task is None or task.status in (
        StorageCleanupStatus.COMPLETED,
        StorageCleanupStatus.CANCELLED,
    ):
        return None
    if task.status == StorageCleanupStatus.RUNNING and not force_reclaim:
        # Someone else already holds a fresh lease -- do not steal work
        # that may genuinely still be in flight elsewhere.
        return None

    lease_token = uuid.uuid4()
    task.status = StorageCleanupStatus.RUNNING
    task.claimed_at = utcnow()
    task.lease_token = lease_token
    task.attempts += 1
    db.commit()
    return task, lease_token


def _complete_claim(
    db: Session,
    task_id: uuid.UUID,
    lease_token: uuid.UUID,
    *,
    failed: bool,
    error: str | None = None,
) -> None:
    """Record the outcome of a claimed task, revalidating id *and* lease
    token before mutating anything.

    If no row matches both, this lease has been superseded by a fresher
    claim (e.g. a stale-recovery sweep reclaimed it) since it was taken:
    the current lease holder owns finishing the task, so this is a no-op
    -- it must never mutate the task or release accounting it no longer
    owns.

    Lock ordering: every other lock-acquiring path in this module (and in
    the routers) locks User first, then Project/Asset, then Task --
    otherwise two transactions taking those locks in opposite orders could
    deadlock on Postgres. A completion that touches asset accounting must
    follow that same order, so this uses a *nonlocking* preview to
    discover the task's asset/owner, locks User, then Asset, and only as
    the final, authoritative step re-locks the Task row (revalidating the
    exact id+lease match) before committing any mutation. The Task row is
    therefore never held while a User lock is requested.
    """
    if failed:
        # No asset/accounting mutation on this path -- a direct Task-only
        # lock is safe and matches every other Task-only completion.
        task = db.execute(
            select(StorageCleanupTask)
            .where(StorageCleanupTask.id == task_id, StorageCleanupTask.lease_token == lease_token)
            .with_for_update()
        ).scalar_one_or_none()
        if task is None:
            return
        task.status = StorageCleanupStatus.FAILED
        task.last_error = error
        db.commit()
        return

    # Nonlocking preview: discover which asset (if any) this task refers
    # to without holding any row lock yet. If the lease has already been
    # superseded, there is nothing to do and no lock is ever taken.
    preview_task = db.execute(
        select(StorageCleanupTask).where(
            StorageCleanupTask.id == task_id, StorageCleanupTask.lease_token == lease_token
        )
    ).scalar_one_or_none()
    if preview_task is None:
        return

    video_asset_id = preview_task.video_asset_id
    if video_asset_id is None:
        # No asset is involved, so there is no User/Asset lock order to
        # respect -- a direct Task-only lock is sufficient.
        task = db.execute(
            select(StorageCleanupTask)
            .where(StorageCleanupTask.id == task_id, StorageCleanupTask.lease_token == lease_token)
            .with_for_update()
        ).scalar_one_or_none()
        if task is None:
            return
        task.status = StorageCleanupStatus.COMPLETED
        task.completed_at = utcnow()
        db.commit()
        return

    preview_asset = db.get(VideoAsset, video_asset_id)
    if preview_asset is None:
        task = db.execute(
            select(StorageCleanupTask)
            .where(StorageCleanupTask.id == task_id, StorageCleanupTask.lease_token == lease_token)
            .with_for_update()
        ).scalar_one_or_none()
        if task is None:
            return
        task.status = StorageCleanupStatus.COMPLETED
        task.completed_at = utcnow()
        db.commit()
        return

    # Lock the owning User before mutating accounting fields, per the
    # User-first locking discipline used everywhere else that writes
    # ledger/reservation state.
    db.execute(select(User).where(User.id == preview_asset.owner_id).with_for_update()).scalar_one()
    # populate_existing=True: this asset row may already be present in
    # this session's identity map, and a concurrent release (e.g. by
    # another claimer of this same task, or a project-delete transaction)
    # must be observed here rather than returning stale in-memory
    # attributes, which would risk double-releasing.
    video_asset = db.execute(
        select(VideoAsset)
        .where(VideoAsset.id == video_asset_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()

    # Only now, with User and Asset already locked, take the final,
    # authoritative Task lock and revalidate the exact lease. If it no
    # longer matches, a fresher claim has taken over since the preview --
    # commit (releasing the User/Asset locks) and make no mutation.
    task = db.execute(
        select(StorageCleanupTask)
        .where(StorageCleanupTask.id == task_id, StorageCleanupTask.lease_token == lease_token)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if task is None:
        db.commit()
        return

    task.status = StorageCleanupStatus.COMPLETED
    completed_at = utcnow()
    task.completed_at = completed_at

    if video_asset is not None:
        # Only now that the storage-side operation has actually succeeded
        # is it safe to release outstanding reservations and previously
        # *counted* stored bytes. Analysis/storage reservations cover an
        # ABORT_MULTIPART task whose upload never finished (e.g. a
        # multipart-expiry sweep); counted bytes cover a DELETE_OBJECT
        # task for an already-uploaded object. Both helpers are idempotent
        # no-ops if already released, so calling all of them
        # unconditionally is safe regardless of which applies to this
        # task.
        reservation_service.release_analysis_reservation(db, video_asset)
        reservation_service.release_storage_reservation(db, video_asset)
        reservation_service.release_counted_storage_bytes(db, video_asset)
        if (
            video_asset.source_expired_at is None
            and video_asset.status == VideoAssetStatus.CLEANUP_PENDING
            and task.operation == StorageCleanupOperation.DELETE_OBJECT
            and task.object_key == video_asset.object_key
            and video_asset.retention_expires_at is not None
            and ensure_aware(video_asset.retention_expires_at)
            <= ensure_aware(completed_at)
            and db.execute(
                select(Project.id).where(
                    Project.id == video_asset.project_id,
                    Project.deleted_at.is_(None),
                )
            ).first()
            is not None
            and db.execute(
                select(AnalysisJob.id).where(
                    AnalysisJob.video_asset_id == video_asset.id,
                    AnalysisJob.status == JobStatus.SUCCEEDED,
                    AnalysisJob.report_object_key.is_not(None),
                )
            ).first()
            is not None
        ):
            video_asset.source_expired_at = completed_at
        terminal_status = (
            VideoAssetStatus.SOURCE_EXPIRED
            if video_asset.source_expired_at is not None
            else VideoAssetStatus.UPLOAD_ABORTED
        )
        if video_asset.status != terminal_status:
            video_asset.status = terminal_status

    db.commit()


def claim_and_process(db: Session, task_id: uuid.UUID, storage: ObjectStorage) -> None:
    """Idempotently perform the durable operation described by the task
    identified by ``task_id``.

    Safe to call more than once for the same task: an already-``COMPLETED``
    task is a no-op, and both ``delete_object`` and
    ``abort_multipart_upload`` are themselves idempotent against a repeat
    call for an object/upload that is already gone. Never steals a fresh
    lease held by someone else -- see the module docstring for the full
    claim/complete protocol.
    """
    claimed = _claim_task_for_processing(db, task_id, force_reclaim=False)
    if claimed is None:
        return
    task, lease_token = claimed
    _process_claim(db, task, lease_token, storage)


def _process_claim(
    db: Session, task: StorageCleanupTask, lease_token: uuid.UUID, storage: ObjectStorage
) -> None:
    """Dispatch a freshly claimed task to the appropriate processing path.

    An ``ABORT_MULTIPART`` task tied to a specific ``VideoAsset`` needs the
    User->Asset->Task lock discipline in
    ``_process_abort_multipart_with_asset`` to make the finalize-vs-expiry-
    abort race deterministic. Every other task (``DELETE_OBJECT``, or an
    ``ABORT_MULTIPART`` task with no asset -- e.g. the ``initiate_upload``
    IntegrityError-recovery path) keeps the original lock-free-during-the-
    external-call pattern.
    """
    if task.operation == StorageCleanupOperation.ABORT_MULTIPART and task.video_asset_id is not None:
        _process_abort_multipart_with_asset(db, task, lease_token, storage)
        return
    _run_lock_free_and_complete(db, task, lease_token, storage)


def _run_lock_free_and_complete(
    db: Session, task: StorageCleanupTask, lease_token: uuid.UUID, storage: ObjectStorage
) -> None:
    task_id = task.id
    operation = task.operation
    object_key = task.object_key
    upload_id = task.upload_id

    try:
        if operation == StorageCleanupOperation.DELETE_OBJECT:
            storage.delete_object(object_key=object_key)
        else:
            assert upload_id is not None
            storage.abort_multipart_upload(object_key=object_key, upload_id=upload_id)
    except ClientError as exc:
        _complete_claim(db, task_id, lease_token, failed=True, error=str(exc))
        return

    _complete_claim(db, task_id, lease_token, failed=False)


def _process_abort_multipart_with_asset(
    db: Session, task: StorageCleanupTask, lease_token: uuid.UUID, storage: ObjectStorage
) -> None:
    """Process a claimed ``ABORT_MULTIPART`` task that targets a specific
    ``VideoAsset``, holding User->Asset->Task locks through the external S3
    call and the accounting/status commit.

    This is what makes the finalize-vs-expiry-abort race deterministic:
    whichever side (this worker, or a concurrent finalize call durably
    claiming ``FINALIZING``) manages to lock User->Asset first and commit
    wins. If finalize wins first, it cancels/supersedes this task's lease
    (``cancel_scheduled_task``) before this worker ever reaches its own
    lease re-check below, which then finds the lease gone and safely
    no-ops without ever calling S3. If this worker wins first, it holds the
    locks through the S3 call and the status/accounting commit, so
    finalize -- arriving after -- observes the resulting terminal asset
    status (``UPLOAD_ABORTED``) via its own existing status check instead
    of racing ahead to complete.

    A scheduled multipart-expiry task and a manual/deletion-triggered abort
    task are both eligible while the asset is either still exactly
    ``UPLOAD_INITIATED`` (nobody has started finalizing it yet) or already
    ``CLEANUP_PENDING`` (a project delete has already tombstoned it and
    decided an abort is warranted) -- ``abort_multipart_upload`` is itself
    idempotent, so processing it in either state is always safe. Any other
    status (``FINALIZING``, ``UPLOADED``, ...), or a lease that has since
    been superseded, cancels the task (or leaves it cancelled) without
    ever calling storage: a task queued via ``get_or_create_cleanup_task``
    may be an *existing* task reused from an earlier scheduling context
    (so its own ``not_before`` cannot reliably distinguish "this call is a
    scheduled sweep" from "this call is an immediate manual abort" -- the
    asset's current status is the authoritative signal instead).
    """
    task_id = task.id
    video_asset_id = task.video_asset_id
    assert video_asset_id is not None

    preview_asset = db.get(VideoAsset, video_asset_id)
    if preview_asset is None:
        _complete_claim(db, task_id, lease_token, failed=True, error="video asset no longer exists")
        return
    owner_id = preview_asset.owner_id

    # Lock order: User, then the VideoAsset, then (below) the Task -- the
    # same relative order finalize uses (User->Project->Asset->Task), so
    # neither side can deadlock against the other regardless of who wins.
    db.execute(select(User).where(User.id == owner_id).with_for_update()).scalar_one()
    # populate_existing=True: this asset row may already be present in
    # this session's identity map, and a concurrent finalize/abort commit
    # must be observed here rather than returning stale in-memory
    # attributes.
    video_asset = db.execute(
        select(VideoAsset)
        .where(VideoAsset.id == video_asset_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()

    # Re-verify this exact lease under the Task lock, now that User/Asset
    # are held: a concurrent finalize call may have superseded it (set
    # CANCELLED and rotated the lease token) between the initial claim and
    # this point.
    current_task = db.execute(
        select(StorageCleanupTask)
        .where(StorageCleanupTask.id == task_id, StorageCleanupTask.lease_token == lease_token)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if current_task is None:
        # Lease superseded -- the current lease holder (finalize's
        # cancellation, in practice) owns this task's outcome now.
        db.commit()
        return

    eligible_statuses = (VideoAssetStatus.UPLOAD_INITIATED, VideoAssetStatus.CLEANUP_PENDING)
    if video_asset is None or video_asset.status not in eligible_statuses:
        # No longer eligible for an abort (finalize already claimed
        # FINALIZING/completed, or another operation moved the asset on)
        # -- never call S3 for a request that no longer applies.
        current_task.status = StorageCleanupStatus.CANCELLED
        db.commit()
        return

    object_key = current_task.object_key
    upload_id = current_task.upload_id
    assert upload_id is not None
    try:
        storage.abort_multipart_upload(object_key=object_key, upload_id=upload_id)
    except ClientError as exc:
        current_task.status = StorageCleanupStatus.FAILED
        current_task.last_error = str(exc)
        db.commit()
        return

    reservation_service.release_analysis_reservation(db, video_asset)
    reservation_service.release_storage_reservation(db, video_asset)
    video_asset.status = VideoAssetStatus.UPLOAD_ABORTED
    current_task.status = StorageCleanupStatus.COMPLETED
    current_task.completed_at = utcnow()
    db.commit()


def _claim_next_due_task(
    db: Session,
    *,
    exclude_ids: set[uuid.UUID],
    reference: datetime,
    stale_before: datetime,
) -> tuple[StorageCleanupTask, uuid.UUID] | None:
    """Atomically select and claim exactly one currently-eligible task.

    Re-evaluates eligibility (due ``PENDING``/``FAILED``, or stale
    ``RUNNING``) fresh at the moment of claiming -- never from an earlier
    snapshot -- so a task that a concurrent claimer has since taken with a
    fresh lease (or already completed) is never stolen. ``exclude_ids``
    lets one sweep skip a task it has already attempted this pass, so a
    single persistently-failing task cannot spin the sweep in place
    without ever reaching other eligible tasks; every other still-eligible
    task is considered in ``created_at`` order.
    """
    conditions = [
        or_(
            and_(
                StorageCleanupTask.status.in_(
                    (StorageCleanupStatus.PENDING, StorageCleanupStatus.FAILED)
                ),
                or_(
                    StorageCleanupTask.not_before.is_(None),
                    StorageCleanupTask.not_before <= reference,
                ),
            ),
            and_(
                StorageCleanupTask.status == StorageCleanupStatus.RUNNING,
                or_(
                    StorageCleanupTask.claimed_at.is_(None),
                    StorageCleanupTask.claimed_at < stale_before,
                ),
            ),
        )
    ]
    if exclude_ids:
        conditions.append(StorageCleanupTask.id.notin_(exclude_ids))
    stmt = (
        select(StorageCleanupTask)
        .where(*conditions)
        .order_by(StorageCleanupTask.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    task = db.execute(stmt).scalars().first()
    if task is None:
        return None

    lease_token = uuid.uuid4()
    task.status = StorageCleanupStatus.RUNNING
    task.claimed_at = utcnow()
    task.lease_token = lease_token
    task.attempts += 1
    db.commit()
    return task, lease_token


def retry_pending_cleanup_tasks(
    db: Session,
    storage: ObjectStorage,
    *,
    limit: int = 50,
    stale_after_seconds: int = 300,
    now: datetime | None = None,
) -> int:
    """Explicit worker/ops seam: scan and retry outstanding cleanup tasks.

    Repeatedly claims and processes exactly one currently-eligible task at
    a time (via ``_claim_next_due_task``, using ``SELECT ... FOR UPDATE
    SKIP LOCKED`` where the backend supports it -- e.g. Postgres; SQLite
    ignores the locking hint but still simply returns the matching row),
    up to ``limit`` iterations. Callable on demand by an operator, a
    management command, or a future worker process -- no scheduler/Celery
    is introduced by this function itself, but this is the real retry
    path: it actually scans for and retries outstanding work.

    Because each claim re-evaluates eligibility fresh rather than trusting
    an earlier batch snapshot, this sweep can never steal a task that an
    independent caller has since (and legitimately) claimed with its own
    fresh lease while this sweep was still working through earlier tasks.

    Matches due ``PENDING``/``FAILED`` tasks (``not_before``, if any,
    already elapsed) plus ``RUNNING`` tasks whose ``claimed_at`` is
    missing or older than ``stale_after_seconds``: a worker that crashed
    after claiming a task (setting it ``RUNNING``) but before completing
    it would otherwise leave that task stuck forever. Since delete/abort
    are idempotent against a real backend, safely reclaiming such a stale
    claim is recoverable even if the original attempt's external call
    actually already succeeded. A ``RUNNING`` task claimed more recently
    than the cutoff is left alone -- it may still be genuinely in flight
    elsewhere.

    A single task that keeps failing within one sweep is attempted at
    most once per call (tracked locally via ``attempted_ids``) so it
    cannot spin the sweep in place instead of reaching other eligible
    tasks; it remains ``FAILED``/retryable for the next sweep. Returns the
    number of tasks this sweep attempted.
    """
    reference = now if now is not None else utcnow()
    stale_before = reference - timedelta(seconds=stale_after_seconds)
    attempted_ids: set[uuid.UUID] = set()
    processed = 0
    for _ in range(limit):
        claimed = _claim_next_due_task(
            db, exclude_ids=attempted_ids, reference=reference, stale_before=stale_before
        )
        if claimed is None:
            break
        task, lease_token = claimed
        attempted_ids.add(task.id)
        _process_claim(db, task, lease_token, storage)
        processed += 1
    return processed



def run_due_storage_cleanup_sweep(
    db: Session,
    storage: ObjectStorage,
    *,
    now: datetime | None = None,
    limit: int = 50,
    stale_after_seconds: int = 300,
) -> int:
    """Explicit callable ops/worker seam: process every due cleanup task.

    This is what a future periodic caller (a Celery Beat schedule, a cron
    job, a management command, or a manual admin action) invokes -- no
    scheduler/Celery is introduced here, but this is the real entry point
    such a schedule would call. It processes any due ``PENDING``/``FAILED``
    task (including a scheduled ``ABORT_MULTIPART`` expiry task whose
    ``not_before`` has elapsed) plus stale ``RUNNING`` tasks left behind by
    a crashed claimer, via ``retry_pending_cleanup_tasks``.
    """
    return retry_pending_cleanup_tasks(
        db, storage, limit=limit, stale_after_seconds=stale_after_seconds, now=now
    )
