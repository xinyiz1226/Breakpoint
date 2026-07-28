"""Service-seam tests for the durable storage-cleanup outbox.

``claim_and_process`` is the "worker" that actually performs a durable
``StorageCleanupTask``'s S3 side effect. These tests exercise it directly
against the in-memory ``FakeObjectStorage`` rather than through an API
endpoint, since the cleanup task itself -- not any particular caller -- is
the seam under test.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models.cleanup import StorageCleanupTask
from app.models.enums import StorageCleanupOperation, StorageCleanupStatus, VideoAssetStatus
from app.services.storage import ObjectMetadata
from app.services.storage_cleanup import claim_and_process
from tests.fakes import FakeObjectStorage


def _create_delete_task(
    db: Session, *, object_key: str, video_asset_id: uuid.UUID | None = None
) -> StorageCleanupTask:
    task = StorageCleanupTask(
        project_id=uuid.uuid4(),
        video_asset_id=video_asset_id,
        object_key=object_key,
        operation=StorageCleanupOperation.DELETE_OBJECT,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def test_claim_and_process_deletes_object_and_marks_completed(
    db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    object_key = "projects/x/source/y.mp4"
    fake_storage.objects[object_key] = ObjectMetadata(size_bytes=10, content_type="video/mp4")
    task = _create_delete_task(db_session, object_key=object_key)

    claim_and_process(db_session, task.id, fake_storage)

    assert task.status == StorageCleanupStatus.COMPLETED
    assert task.attempts == 1
    assert task.completed_at is not None
    assert object_key in fake_storage.deleted_object_keys
    assert object_key not in fake_storage.objects


def test_claim_and_process_preserves_retryable_task_on_delete_failure(
    db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    object_key = "projects/x/source/z.mp4"
    fake_storage.objects[object_key] = ObjectMetadata(size_bytes=10, content_type="video/mp4")
    fake_storage.fail_next_deletes = 1
    task = _create_delete_task(db_session, object_key=object_key)

    claim_and_process(db_session, task.id, fake_storage)

    assert task.status == StorageCleanupStatus.FAILED
    assert task.attempts == 1
    assert task.last_error is not None
    assert task.completed_at is None
    # The object was never actually deleted -- no untracked/orphaned object,
    # and the durable task is still there to retry.
    assert object_key in fake_storage.objects

    # A later retry (same task, now that storage recovers) succeeds and
    # completes it -- attempts accumulate rather than resetting.
    claim_and_process(db_session, task.id, fake_storage)
    assert task.status == StorageCleanupStatus.COMPLETED
    assert task.attempts == 2
    assert object_key not in fake_storage.objects


def test_claim_and_process_marks_video_asset_aborted_when_cleanup_completes(
    db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    from tests.conftest import create_user
    from app.models.project import Project
    from app.models.video import VideoAsset

    owner = create_user(db_session, email="owner@example.com", password="valid-test-password")
    project = Project(owner_id=owner.id, name="Match")
    db_session.add(project)
    db_session.flush()
    video_asset = VideoAsset(
        project_id=project.id,
        owner_id=owner.id,
        object_key="projects/x/source/w.mp4",
        original_filename="w.mp4",
        content_type="video/mp4",
        declared_size_bytes=10,
        declared_duration_seconds=5.0,
        status=VideoAssetStatus.CLEANUP_PENDING,
        upload_id="upload-1",
        part_count=1,
    )
    db_session.add(video_asset)
    db_session.commit()
    db_session.refresh(video_asset)

    fake_storage.objects[video_asset.object_key] = ObjectMetadata(size_bytes=10, content_type="video/mp4")
    task = _create_delete_task(
        db_session, object_key=video_asset.object_key, video_asset_id=video_asset.id
    )

    claim_and_process(db_session, task.id, fake_storage)

    assert task.status == StorageCleanupStatus.COMPLETED
    db_session.refresh(video_asset)
    assert video_asset.status == VideoAssetStatus.UPLOAD_ABORTED


# --- Item 2: counted-byte release only after DELETE_OBJECT succeeds -------------


def test_claim_and_process_releases_counted_storage_bytes_only_on_delete_success(
    db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    """storage_counted_bytes -- and the ledger balance it backs -- must stay
    charged while a DELETE_OBJECT cleanup is still failing/retrying, and
    only be released once the delete actually succeeds. Releasing it
    eagerly (e.g. at project-delete time, before cleanup even runs) would
    let a user keep the object's bytes occupied in storage while no longer
    being charged for them.
    """
    from tests.conftest import create_user
    from app.models.project import Project
    from app.models.video import VideoAsset
    from app.models.enums import QuotaLedgerEventType
    from app.services import quota as quota_service

    owner = create_user(db_session, email="owner@example.com", password="valid-test-password")
    project = Project(owner_id=owner.id, name="Match")
    db_session.add(project)
    db_session.flush()
    video_asset = VideoAsset(
        project_id=project.id,
        owner_id=owner.id,
        object_key="projects/x/source/counted.mp4",
        original_filename="counted.mp4",
        content_type="video/mp4",
        declared_size_bytes=1000,
        declared_duration_seconds=5.0,
        status=VideoAssetStatus.CLEANUP_PENDING,
        upload_id="upload-1",
        part_count=1,
        storage_counted_bytes=1000,
    )
    db_session.add(video_asset)
    db_session.flush()
    quota_service.record_ledger_event(
        db_session,
        user_id=owner.id,
        event_type=QuotaLedgerEventType.UPLOAD_FINALIZED,
        video_asset_id=video_asset.id,
        bytes_delta=1000,
    )
    db_session.commit()
    db_session.refresh(video_asset)

    fake_storage.objects[video_asset.object_key] = ObjectMetadata(
        size_bytes=1000, content_type="video/mp4"
    )
    fake_storage.fail_next_deletes = 1
    task = _create_delete_task(
        db_session, object_key=video_asset.object_key, video_asset_id=video_asset.id
    )

    claim_and_process(db_session, task.id, fake_storage)

    assert task.status == StorageCleanupStatus.FAILED
    db_session.refresh(video_asset)
    assert video_asset.storage_counted_bytes == 1000
    assert quota_service.storage_bytes_used(db_session, owner.id) == 1000

    # Retry succeeds now that storage recovers: only now is the balance
    # released.
    claim_and_process(db_session, task.id, fake_storage)

    assert task.status == StorageCleanupStatus.COMPLETED
    db_session.refresh(video_asset)
    assert video_asset.storage_counted_bytes == 0
    assert quota_service.storage_bytes_used(db_session, owner.id) == 0


# --- Item 3: explicit retry sweep over pending/failed cleanup tasks -------------


def test_retry_pending_cleanup_tasks_processes_pending_and_failed_ignores_completed(
    db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    from app.services.storage_cleanup import retry_pending_cleanup_tasks

    pending_key = "projects/x/source/pending.mp4"
    failed_key = "projects/x/source/failed.mp4"
    completed_key = "projects/x/source/completed.mp4"
    fake_storage.objects[pending_key] = ObjectMetadata(size_bytes=5, content_type="video/mp4")
    fake_storage.objects[failed_key] = ObjectMetadata(size_bytes=5, content_type="video/mp4")
    fake_storage.objects[completed_key] = ObjectMetadata(size_bytes=5, content_type="video/mp4")

    pending_task = _create_delete_task(db_session, object_key=pending_key)

    failed_task = _create_delete_task(db_session, object_key=failed_key)
    failed_task.status = StorageCleanupStatus.FAILED
    failed_task.attempts = 1
    failed_task.last_error = "simulated earlier failure"

    completed_task = _create_delete_task(db_session, object_key=completed_key)
    completed_task.status = StorageCleanupStatus.COMPLETED
    completed_task.attempts = 1
    db_session.commit()

    processed = retry_pending_cleanup_tasks(db_session, fake_storage, limit=10)

    # Only the pending and failed tasks are swept; the already-completed
    # one is left untouched.
    assert processed == 2

    db_session.refresh(pending_task)
    assert pending_task.status == StorageCleanupStatus.COMPLETED
    assert pending_key not in fake_storage.objects

    db_session.refresh(failed_task)
    assert failed_task.status == StorageCleanupStatus.COMPLETED
    assert failed_task.attempts == 2
    assert failed_key not in fake_storage.objects

    db_session.refresh(completed_task)
    assert completed_task.attempts == 1
    assert completed_key in fake_storage.objects


def test_retry_pending_cleanup_tasks_leaves_still_failing_task_retryable(
    db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    from app.services.storage_cleanup import retry_pending_cleanup_tasks

    object_key = "projects/x/source/still-failing.mp4"
    fake_storage.objects[object_key] = ObjectMetadata(size_bytes=5, content_type="video/mp4")
    fake_storage.fail_next_deletes = 1
    task = _create_delete_task(db_session, object_key=object_key)

    processed = retry_pending_cleanup_tasks(db_session, fake_storage, limit=10)

    assert processed == 1
    db_session.refresh(task)
    assert task.status == StorageCleanupStatus.FAILED
    assert object_key in fake_storage.objects

    # A later sweep, once storage recovers, finds and completes it.
    retry_pending_cleanup_tasks(db_session, fake_storage, limit=10)
    db_session.refresh(task)
    assert task.status == StorageCleanupStatus.COMPLETED
    assert object_key not in fake_storage.objects


# --- Final review item 3: stale RUNNING crash recovery -------------------------


def test_retry_pending_cleanup_tasks_reclaims_stale_running_task(
    db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    """A task left ``RUNNING`` by a worker that crashed mid-attempt must
    eventually be reclaimed -- delete/abort are idempotent against a real
    backend, so retrying it is safe -- rather than sitting stuck forever
    because the sweep only ever looked at PENDING/FAILED.
    """
    from datetime import timedelta

    from app.models.base import utcnow
    from app.services.storage_cleanup import retry_pending_cleanup_tasks

    object_key = "projects/x/source/stale-running.mp4"
    fake_storage.objects[object_key] = ObjectMetadata(size_bytes=5, content_type="video/mp4")

    task = _create_delete_task(db_session, object_key=object_key)
    task.status = StorageCleanupStatus.RUNNING
    task.attempts = 1
    task.claimed_at = utcnow() - timedelta(seconds=600)
    db_session.commit()

    processed = retry_pending_cleanup_tasks(
        db_session, fake_storage, limit=10, stale_after_seconds=300
    )

    assert processed == 1
    db_session.refresh(task)
    assert task.status == StorageCleanupStatus.COMPLETED
    assert task.attempts == 2
    assert object_key not in fake_storage.objects


def test_retry_pending_cleanup_tasks_does_not_steal_fresh_running_task(
    db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    """A task claimed moments ago by an in-flight worker must not be stolen
    out from under it just because a sweep happens to run concurrently."""
    from app.models.base import utcnow
    from app.services.storage_cleanup import retry_pending_cleanup_tasks

    object_key = "projects/x/source/fresh-running.mp4"
    fake_storage.objects[object_key] = ObjectMetadata(size_bytes=5, content_type="video/mp4")

    task = _create_delete_task(db_session, object_key=object_key)
    task.status = StorageCleanupStatus.RUNNING
    task.attempts = 1
    task.claimed_at = utcnow()
    db_session.commit()

    processed = retry_pending_cleanup_tasks(
        db_session, fake_storage, limit=10, stale_after_seconds=300
    )

    assert processed == 0
    db_session.refresh(task)
    assert task.status == StorageCleanupStatus.RUNNING
    assert task.attempts == 1
    assert object_key in fake_storage.objects


def test_retry_pending_cleanup_tasks_releases_counted_bytes_when_reclaiming_stale_running_task(
    db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    """Accounting release on a reclaimed-and-completed stale task follows
    the same success-only rule as any other retry: still charged while
    stuck, released once the reclaimed attempt actually succeeds."""
    from datetime import timedelta

    from app.models.base import utcnow
    from app.models.enums import QuotaLedgerEventType
    from app.services import quota as quota_service
    from app.services.storage_cleanup import retry_pending_cleanup_tasks
    from tests.conftest import create_user
    from app.models.project import Project
    from app.models.video import VideoAsset

    owner = create_user(db_session, email="owner-stale@example.com", password="password123")
    project = Project(owner_id=owner.id, name="Match")
    db_session.add(project)
    db_session.flush()
    video_asset = VideoAsset(
        project_id=project.id,
        owner_id=owner.id,
        object_key="projects/x/source/stale-counted.mp4",
        original_filename="stale-counted.mp4",
        content_type="video/mp4",
        declared_size_bytes=1000,
        declared_duration_seconds=5.0,
        status=VideoAssetStatus.CLEANUP_PENDING,
        upload_id="upload-1",
        part_count=1,
        storage_counted_bytes=1000,
    )
    db_session.add(video_asset)
    db_session.flush()
    quota_service.record_ledger_event(
        db_session,
        user_id=owner.id,
        event_type=QuotaLedgerEventType.UPLOAD_FINALIZED,
        video_asset_id=video_asset.id,
        bytes_delta=1000,
    )
    db_session.commit()
    db_session.refresh(video_asset)

    fake_storage.objects[video_asset.object_key] = ObjectMetadata(
        size_bytes=1000, content_type="video/mp4"
    )
    task = _create_delete_task(
        db_session, object_key=video_asset.object_key, video_asset_id=video_asset.id
    )
    task.status = StorageCleanupStatus.RUNNING
    task.attempts = 1
    task.claimed_at = utcnow() - timedelta(seconds=600)
    db_session.commit()

    processed = retry_pending_cleanup_tasks(
        db_session, fake_storage, limit=10, stale_after_seconds=300
    )

    assert processed == 1
    db_session.refresh(task)
    assert task.status == StorageCleanupStatus.COMPLETED
    db_session.refresh(video_asset)
    assert video_asset.storage_counted_bytes == 0
    assert quota_service.storage_bytes_used(db_session, owner.id) == 0


# --- Rereview item 3: atomic claim/lease + fresh accounting ---------------


def test_claim_and_process_does_not_steal_a_fresh_running_lease(
    db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    """A task already RUNNING with a lease claimed moments ago by another
    caller must not be reprocessed by a second, direct claim_and_process
    call -- only a sweep that has already verified staleness itself may
    force a reclaim."""
    from app.models.base import utcnow

    object_key = "projects/x/source/lease-fresh.mp4"
    fake_storage.objects[object_key] = ObjectMetadata(size_bytes=5, content_type="video/mp4")
    task = _create_delete_task(db_session, object_key=object_key)
    original_lease = uuid.uuid4()
    task.status = StorageCleanupStatus.RUNNING
    task.claimed_at = utcnow()
    task.lease_token = original_lease
    task.attempts = 1
    db_session.commit()

    claim_and_process(db_session, task.id, fake_storage)

    db_session.refresh(task)
    assert task.status == StorageCleanupStatus.RUNNING
    assert task.lease_token == original_lease
    assert task.attempts == 1
    # The object was never touched -- this call was a no-op.
    assert object_key in fake_storage.objects


def test_sweep_reclaiming_a_stale_running_task_mints_a_fresh_lease_token(
    db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    from datetime import timedelta

    from app.models.base import utcnow
    from app.services.storage_cleanup import retry_pending_cleanup_tasks

    object_key = "projects/x/source/lease-stale.mp4"
    fake_storage.objects[object_key] = ObjectMetadata(size_bytes=5, content_type="video/mp4")
    task = _create_delete_task(db_session, object_key=object_key)
    stale_lease = uuid.uuid4()
    task.status = StorageCleanupStatus.RUNNING
    task.claimed_at = utcnow() - timedelta(seconds=600)
    task.lease_token = stale_lease
    task.attempts = 1
    db_session.commit()

    processed = retry_pending_cleanup_tasks(db_session, fake_storage, limit=10, stale_after_seconds=300)

    assert processed == 1
    db_session.refresh(task)
    assert task.status == StorageCleanupStatus.COMPLETED
    assert task.lease_token is not None
    assert task.lease_token != stale_lease


def test_a_superseded_lease_completion_cannot_mutate_or_release_again(
    db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    """Simulates: caller A claims a task (gets lease A). Before A's
    completion transaction runs, a stale-recovery sweep (caller B) reclaims
    the same task with a fresh lease B and completes it successfully. When
    A's own (now-superseded) completion attempt finally runs, it must
    observe that its lease no longer matches and make no further mutation
    or accounting release -- so accounting is released exactly once."""
    from app.models.enums import QuotaLedgerEventType
    from app.models.project import Project
    from app.models.video import VideoAsset
    from app.services import quota as quota_service
    from app.services.storage_cleanup import _claim_task_for_processing, _complete_claim
    from tests.conftest import create_user

    owner = create_user(db_session, email="lease-theft@example.com", password="lease-theft-password-1")
    project = Project(owner_id=owner.id, name="Match")
    db_session.add(project)
    db_session.flush()
    video_asset = VideoAsset(
        project_id=project.id,
        owner_id=owner.id,
        object_key="projects/x/source/lease-theft.mp4",
        original_filename="lease-theft.mp4",
        content_type="video/mp4",
        declared_size_bytes=1000,
        declared_duration_seconds=5.0,
        status=VideoAssetStatus.CLEANUP_PENDING,
        upload_id="upload-1",
        part_count=1,
        storage_counted_bytes=1000,
    )
    db_session.add(video_asset)
    db_session.flush()
    quota_service.record_ledger_event(
        db_session,
        user_id=owner.id,
        event_type=QuotaLedgerEventType.UPLOAD_FINALIZED,
        video_asset_id=video_asset.id,
        bytes_delta=1000,
    )
    db_session.commit()
    db_session.refresh(video_asset)

    object_key = video_asset.object_key
    fake_storage.objects[object_key] = ObjectMetadata(size_bytes=1000, content_type="video/mp4")
    task = _create_delete_task(db_session, object_key=object_key, video_asset_id=video_asset.id)
    task_id = task.id

    # Caller A claims the task (lease A) but does not complete yet.
    claim_a = _claim_task_for_processing(db_session, task_id)
    assert claim_a is not None
    _task_a, lease_a = claim_a

    # A stale-recovery sweep force-reclaims the same task with a fresh
    # lease B (simulating a crash-recovery steal), performs the delete, and
    # completes it successfully.
    claim_b = _claim_task_for_processing(db_session, task_id, force_reclaim=True)
    assert claim_b is not None
    _task_b, lease_b = claim_b
    assert lease_b != lease_a
    fake_storage.delete_object(object_key=object_key)
    _complete_claim(db_session, task_id, lease_b, failed=False)

    db_session.refresh(task)
    assert task.status == StorageCleanupStatus.COMPLETED
    db_session.refresh(video_asset)
    assert video_asset.storage_counted_bytes == 0
    assert quota_service.storage_bytes_used(db_session, owner.id) == 0

    # A's own completion attempt, using its now-superseded lease A, must be
    # a pure no-op: it does not re-mutate the task and does not release
    # accounting a second time (which would go negative).
    _complete_claim(db_session, task_id, lease_a, failed=False)

    db_session.refresh(task)
    assert task.status == StorageCleanupStatus.COMPLETED
    db_session.refresh(video_asset)
    assert video_asset.storage_counted_bytes == 0
    assert quota_service.storage_bytes_used(db_session, owner.id) == 0


# --- Rereview item 4: bounded multipart + expiry cleanup sweep -----------------


def _create_upload_initiated_asset(
    db: Session,
    *,
    owner_id,
    object_key: str,
    upload_id: str = "upload-expiry-1",
    analysis_reserved_seconds: float = 600.0,
    storage_reserved_bytes: int = 1000,
):
    from app.models.enums import QuotaLedgerEventType
    from app.models.project import Project
    from app.models.video import VideoAsset
    from app.services import quota as quota_service

    project = Project(owner_id=owner_id, name=f"Expiry {object_key}")
    db.add(project)
    db.flush()
    video_asset = VideoAsset(
        project_id=project.id,
        owner_id=owner_id,
        object_key=object_key,
        original_filename="expiring.mp4",
        content_type="video/mp4",
        declared_size_bytes=storage_reserved_bytes,
        declared_duration_seconds=analysis_reserved_seconds,
        status=VideoAssetStatus.UPLOAD_INITIATED,
        upload_id=upload_id,
        part_count=1,
        analysis_reserved_seconds=analysis_reserved_seconds,
        storage_reserved_bytes=storage_reserved_bytes,
    )
    db.add(video_asset)
    db.flush()
    # Record the reservation ledger events a real initiate_upload call
    # would have made, so a later release nets to zero rather than going
    # negative.
    quota_service.record_ledger_event(
        db,
        user_id=owner_id,
        event_type=QuotaLedgerEventType.ANALYSIS_RESERVED,
        video_asset_id=video_asset.id,
        seconds_delta=analysis_reserved_seconds,
    )
    quota_service.record_ledger_event(
        db,
        user_id=owner_id,
        event_type=QuotaLedgerEventType.STORAGE_RESERVED,
        video_asset_id=video_asset.id,
        bytes_delta=storage_reserved_bytes,
    )
    db.flush()
    return video_asset


def test_sweep_ignores_an_abort_multipart_task_before_its_not_before(
    db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    from datetime import timedelta

    from app.models.base import utcnow
    from app.services.storage_cleanup import run_due_storage_cleanup_sweep
    from tests.conftest import create_user

    owner = create_user(db_session, email="expiry-early@example.com", password="expiry-test-password-1")
    object_key = "projects/x/source/expiry-early.mp4"
    video_asset = _create_upload_initiated_asset(db_session, owner_id=owner.id, object_key=object_key)
    task = StorageCleanupTask(
        project_id=video_asset.project_id,
        video_asset_id=video_asset.id,
        object_key=object_key,
        upload_id=video_asset.upload_id,
        operation=StorageCleanupOperation.ABORT_MULTIPART,
        not_before=utcnow() + timedelta(hours=1),
    )
    db_session.add(task)
    db_session.commit()

    processed = run_due_storage_cleanup_sweep(db_session, fake_storage)

    assert processed == 0
    db_session.refresh(task)
    assert task.status == StorageCleanupStatus.PENDING


def test_sweep_aborts_expired_multipart_and_releases_both_reservations(
    db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    from datetime import timedelta

    from app.models.base import utcnow
    from app.services import quota as quota_service
    from app.services.storage_cleanup import run_due_storage_cleanup_sweep
    from tests.conftest import create_user

    owner = create_user(db_session, email="expiry-due@example.com", password="expiry-test-password-1")
    object_key = "projects/x/source/expiry-due.mp4"
    video_asset = _create_upload_initiated_asset(db_session, owner_id=owner.id, object_key=object_key)
    task = StorageCleanupTask(
        project_id=video_asset.project_id,
        video_asset_id=video_asset.id,
        object_key=object_key,
        upload_id=video_asset.upload_id,
        operation=StorageCleanupOperation.ABORT_MULTIPART,
        not_before=utcnow() - timedelta(minutes=1),
    )
    db_session.add(task)
    db_session.commit()

    processed = run_due_storage_cleanup_sweep(db_session, fake_storage)

    assert processed == 1
    db_session.refresh(task)
    assert task.status == StorageCleanupStatus.COMPLETED
    assert video_asset.upload_id in fake_storage.aborted_upload_ids
    db_session.refresh(video_asset)
    assert video_asset.analysis_reserved_seconds == 0
    assert video_asset.storage_reserved_bytes == 0
    assert video_asset.status == VideoAssetStatus.UPLOAD_ABORTED
    assert quota_service.monthly_analysis_seconds_used(db_session, owner.id) == 0
    assert quota_service.storage_bytes_used(db_session, owner.id) == 0


def test_sweep_leaves_a_failing_expired_abort_retryable(
    db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    from datetime import timedelta

    from app.models.base import utcnow
    from app.services.storage_cleanup import run_due_storage_cleanup_sweep
    from tests.conftest import create_user

    owner = create_user(db_session, email="expiry-fail@example.com", password="expiry-test-password-1")
    object_key = "projects/x/source/expiry-fail.mp4"
    video_asset = _create_upload_initiated_asset(db_session, owner_id=owner.id, object_key=object_key)
    fake_storage.fail_next_aborts = 1
    task = StorageCleanupTask(
        project_id=video_asset.project_id,
        video_asset_id=video_asset.id,
        object_key=object_key,
        upload_id=video_asset.upload_id,
        operation=StorageCleanupOperation.ABORT_MULTIPART,
        not_before=utcnow() - timedelta(minutes=1),
    )
    db_session.add(task)
    db_session.commit()

    processed = run_due_storage_cleanup_sweep(db_session, fake_storage)

    assert processed == 1
    db_session.refresh(task)
    assert task.status == StorageCleanupStatus.FAILED
    assert task.last_error is not None
    db_session.refresh(video_asset)
    # The reservations stay outstanding until the abort actually succeeds --
    # no premature release just because a sweep attempted it.
    assert video_asset.analysis_reserved_seconds == video_asset.declared_duration_seconds
    assert video_asset.storage_reserved_bytes == video_asset.declared_size_bytes

    # A later retry, once storage recovers, succeeds and releases.
    processed_again = run_due_storage_cleanup_sweep(db_session, fake_storage)
    assert processed_again == 1
    db_session.refresh(task)
    assert task.status == StorageCleanupStatus.COMPLETED
    db_session.refresh(video_asset)
    assert video_asset.analysis_reserved_seconds == 0
    assert video_asset.storage_reserved_bytes == 0


def test_cancel_scheduled_task_marks_pending_abort_cancelled(db_session: Session) -> None:
    from app.services.storage_cleanup import cancel_scheduled_task
    from tests.conftest import create_user

    owner = create_user(db_session, email="expiry-cancel@example.com", password="expiry-test-password-1")
    object_key = "projects/x/source/expiry-cancel.mp4"
    video_asset = _create_upload_initiated_asset(db_session, owner_id=owner.id, object_key=object_key)
    task = StorageCleanupTask(
        project_id=video_asset.project_id,
        video_asset_id=video_asset.id,
        object_key=object_key,
        upload_id=video_asset.upload_id,
        operation=StorageCleanupOperation.ABORT_MULTIPART,
    )
    db_session.add(task)
    db_session.commit()

    cancel_scheduled_task(
        db_session, video_asset_id=video_asset.id, operation=StorageCleanupOperation.ABORT_MULTIPART
    )
    db_session.commit()

    db_session.refresh(task)
    assert task.status == StorageCleanupStatus.CANCELLED


# --- Independent review round 2 item 1: batch sweep stale force-reclaim race --
#
# The sweep must never snapshot many task ids up front and then blindly
# force-reclaim each by id: a task that looked like a stale RUNNING (or due
# PENDING/FAILED) candidate when the batch query ran may have since been
# freshly (and legitimately) claimed by an independent caller. Re-evaluating
# eligibility fresh on every single-row claim, rather than trusting an
# earlier snapshot, is what prevents stealing that fresh claim.


def test_sweep_does_not_steal_a_task_freshly_claimed_by_another_session_mid_batch(
    session_factory,
) -> None:
    """Session A's sweep claims and starts processing task1 (the earliest
    due task). While task1's delete is "in flight" (simulated via a
    storage hook), an independent session B freshly claims *and completes*
    task2 -- the next task the sweep's original batch query would have
    seen as eligible. A's sweep must not then steal task2 out from under
    B: it must re-check eligibility at the moment it would claim task2,
    see it is no longer eligible (already COMPLETED), and stop -- not
    force-reclaim it based on the batch's original snapshot. Reservations
    for both tasks' assets must be released exactly once each, and task1
    itself must complete normally rather than being left stranded FAILED
    by this interleaving.
    """
    from datetime import timedelta

    from app.models.base import utcnow
    from app.models.enums import QuotaLedgerEventType
    from app.models.project import Project
    from app.models.video import VideoAsset
    from app.services import quota as quota_service
    from app.services.storage_cleanup import run_due_storage_cleanup_sweep
    from tests.conftest import create_user

    storage = FakeObjectStorage()
    session_a = session_factory()
    session_b = session_factory()
    try:
        owner = create_user(session_a, email="sweep-race@example.com", password="sweep-race-password-1")

        def _make_cleanup_pending_asset(db: Session, *, object_key: str) -> VideoAsset:
            project = Project(owner_id=owner.id, name=f"Sweep race {object_key}")
            db.add(project)
            db.flush()
            video_asset = VideoAsset(
                project_id=project.id,
                owner_id=owner.id,
                object_key=object_key,
                original_filename="race.mp4",
                content_type="video/mp4",
                declared_size_bytes=500,
                declared_duration_seconds=5.0,
                status=VideoAssetStatus.CLEANUP_PENDING,
                upload_id="upload-race",
                part_count=1,
                storage_counted_bytes=500,
            )
            db.add(video_asset)
            db.flush()
            quota_service.record_ledger_event(
                db,
                user_id=owner.id,
                event_type=QuotaLedgerEventType.UPLOAD_FINALIZED,
                video_asset_id=video_asset.id,
                bytes_delta=500,
            )
            db.commit()
            db.refresh(video_asset)
            return video_asset

        key1 = "projects/x/source/sweep-race-1.mp4"
        key2 = "projects/x/source/sweep-race-2.mp4"
        storage.objects[key1] = ObjectMetadata(size_bytes=500, content_type="video/mp4")
        storage.objects[key2] = ObjectMetadata(size_bytes=500, content_type="video/mp4")

        asset1 = _make_cleanup_pending_asset(session_a, object_key=key1)
        asset2 = _make_cleanup_pending_asset(session_a, object_key=key2)

        task1 = StorageCleanupTask(
            project_id=asset1.project_id,
            video_asset_id=asset1.id,
            object_key=key1,
            operation=StorageCleanupOperation.DELETE_OBJECT,
            created_at=utcnow() - timedelta(seconds=10),
        )
        task2 = StorageCleanupTask(
            project_id=asset2.project_id,
            video_asset_id=asset2.id,
            object_key=key2,
            operation=StorageCleanupOperation.DELETE_OBJECT,
            created_at=utcnow() - timedelta(seconds=5),
        )
        session_a.add(task1)
        session_a.add(task2)
        session_a.commit()
        task2_id = task2.id

        def _interleave_from_session_b() -> None:
            # Fires once, during task1's delete_object call: an
            # independent session freshly claims and fully completes
            # task2 before A's sweep loop ever reaches it.
            claim_and_process(session_b, task2_id, storage)

        storage.on_delete_object = _interleave_from_session_b

        processed = run_due_storage_cleanup_sweep(session_a, storage)

        # Only task1 -- task2 was already handled by B before A's own
        # per-iteration eligibility re-check ever considered it.
        assert processed == 1
        assert sorted(storage.deleted_object_keys) == sorted([key1, key2])

        session_a.refresh(task1)
        assert task1.status == StorageCleanupStatus.COMPLETED

        task2_final = session_a.execute(
            select(StorageCleanupTask)
            .where(StorageCleanupTask.id == task2_id)
            .execution_options(populate_existing=True)
        ).scalar_one()
        assert task2_final.status == StorageCleanupStatus.COMPLETED

        # Reservations for both assets released exactly once -- never
        # negative, regardless of which session actually performed the
        # release.
        assert quota_service.storage_bytes_used(session_a, owner.id) == 0
    finally:
        session_a.close()
        session_b.close()


# --- Independent review round 2 item 2: FINALIZING vs already-RUNNING expiry abort --
#
# These use two genuinely independent Session objects (see test_auth.py's
# "Rereview item 1" section for the same pattern) so that a stale
# identity-map read is a real possibility, not merely simulated in-process.


def test_finalize_claiming_first_supersedes_a_running_scheduled_abort_lease(
    session_factory, test_settings
) -> None:
    """Scenario (a): the expiry sweep's worker has already claimed the
    scheduled ABORT_MULTIPART task (RUNNING, lease L) but has not yet
    locked User/Asset or called S3. An independent finalize request then
    durably claims FINALIZING first and, in the same transaction,
    cancels/supersedes the scheduled task's lease. The worker's
    continuation -- still holding its now-stale lease -- must observe the
    supersession before ever calling S3 and must not touch reservations:
    finalize wins this race deterministically.
    """
    from datetime import timedelta

    from app.models.base import utcnow
    from app.models.video import VideoAsset
    from app.routers import uploads as uploads_router
    from app.schemas.video import CompletedPart, FinalizeUploadRequest
    from app.services.storage_cleanup import _claim_task_for_processing, _process_claim
    from tests.conftest import create_user

    storage = FakeObjectStorage()
    session_worker = session_factory()
    session_finalize = session_factory()
    try:
        owner = create_user(
            session_worker, email="race-a@example.com", password="race-a-password-1"
        )
        object_key = "projects/x/source/race-a.mp4"
        upload_id = storage.create_multipart_upload(object_key=object_key, content_type="video/mp4")
        video_asset = _create_upload_initiated_asset(
            session_worker,
            owner_id=owner.id,
            object_key=object_key,
            upload_id=upload_id,
            analysis_reserved_seconds=600.0,
            storage_reserved_bytes=0,
        )
        video_asset_id = video_asset.id
        project_id = video_asset.project_id

        task = StorageCleanupTask(
            project_id=project_id,
            video_asset_id=video_asset_id,
            object_key=object_key,
            upload_id=upload_id,
            operation=StorageCleanupOperation.ABORT_MULTIPART,
            not_before=utcnow() - timedelta(minutes=1),
        )
        session_worker.add(task)
        session_worker.commit()
        task_id = task.id

        # The worker claims the scheduled expiry task (RUNNING + a fresh
        # lease, committed) but has not yet locked User/Asset or called
        # S3.
        claimed = _claim_task_for_processing(session_worker, task_id)
        assert claimed is not None
        claimed_task, lease_token = claimed

        # An independent finalize request, in its own session, durably
        # claims FINALIZING and cancels/supersedes the scheduled task,
        # then runs to completion.
        response = uploads_router.finalize_upload(
            project_id=project_id,
            video_asset_id=video_asset_id,
            payload=FinalizeUploadRequest(
                idempotency_key="race-a", parts=[CompletedPart(part_number=1, etag="etag-1")]
            ),
            db=session_finalize,
            current_user=owner,
            settings=test_settings,
            storage=storage,
        )
        assert response.video_asset.status == VideoAssetStatus.UPLOADED

        # The worker's continuation, using its now-superseded lease, must
        # observe the supersession before ever calling S3 -- it must not
        # abort the multipart finalize just completed, and must not
        # release reservations it no longer owns.
        _process_claim(session_worker, claimed_task, lease_token, storage)

        assert upload_id not in storage.aborted_upload_ids

        final_task = session_worker.execute(
            select(StorageCleanupTask)
            .where(StorageCleanupTask.id == task_id)
            .execution_options(populate_existing=True)
        ).scalar_one()
        assert final_task.status == StorageCleanupStatus.CANCELLED

        final_asset = session_worker.execute(
            select(VideoAsset)
            .where(VideoAsset.id == video_asset_id)
            .execution_options(populate_existing=True)
        ).scalar_one()
        assert final_asset.status == VideoAssetStatus.UPLOADED
        assert final_asset.analysis_reserved_seconds == 600.0
    finally:
        session_worker.close()
        session_finalize.close()


def test_cleanup_winning_the_race_leaves_finalize_observing_aborted_upload(
    session_factory, test_settings
) -> None:
    """Scenario (b): the expiry sweep wins the race -- it locks User then
    Asset before finalize gets a chance to, calls S3 abort, releases both
    reservations, and marks the asset UPLOAD_ABORTED, all before
    committing. An independent finalize request that comes along
    afterward must observe the aborted state and fail safely (409)
    instead of proceeding to FINALIZING or ever calling S3 itself.
    """
    from datetime import timedelta

    from app.models.base import utcnow
    from fastapi import HTTPException
    from app.routers import uploads as uploads_router
    from app.schemas.video import CompletedPart, FinalizeUploadRequest
    from app.services.storage_cleanup import run_due_storage_cleanup_sweep
    from tests.conftest import create_user

    storage = FakeObjectStorage()
    session_cleanup = session_factory()
    session_finalize = session_factory()
    try:
        owner = create_user(
            session_cleanup, email="race-b@example.com", password="race-b-password-1"
        )
        object_key = "projects/x/source/race-b.mp4"
        upload_id = storage.create_multipart_upload(object_key=object_key, content_type="video/mp4")
        video_asset = _create_upload_initiated_asset(
            session_cleanup, owner_id=owner.id, object_key=object_key, upload_id=upload_id
        )
        video_asset_id = video_asset.id
        project_id = video_asset.project_id

        task = StorageCleanupTask(
            project_id=project_id,
            video_asset_id=video_asset_id,
            object_key=object_key,
            upload_id=upload_id,
            operation=StorageCleanupOperation.ABORT_MULTIPART,
            not_before=utcnow() - timedelta(minutes=1),
        )
        session_cleanup.add(task)
        session_cleanup.commit()

        # The expiry sweep wins the race: it locks User -> Asset, calls
        # S3 abort, releases both reservations, marks UPLOAD_ABORTED, and
        # commits -- before finalize ever gets a chance to lock the same
        # rows.
        processed = run_due_storage_cleanup_sweep(session_cleanup, storage)
        assert processed == 1
        assert upload_id in storage.aborted_upload_ids

        # An independent finalize request now locks and observes the
        # aborted state rather than being able to claim FINALIZING.
        with pytest.raises(HTTPException) as excinfo:
            uploads_router.finalize_upload(
                project_id=project_id,
                video_asset_id=video_asset_id,
                payload=FinalizeUploadRequest(
                    idempotency_key="race-b", parts=[CompletedPart(part_number=1, etag="etag-1")]
                ),
                db=session_finalize,
                current_user=owner,
                settings=test_settings,
                storage=storage,
            )
        assert excinfo.value.status_code == 409
        # Finalize never got far enough to call S3 itself.
        assert upload_id not in storage.completed_upload_ids
    finally:
        session_cleanup.close()
        session_finalize.close()


# --- Final review: completion must never hold Task while waiting for User ----
#
# Every lock-acquiring path in this module (and in the routers) follows the
# global User -> Asset -> Task order to avoid a Postgres deadlock: if one
# transaction locked Task then User while another locked User then Task,
# they could each wait on a row the other already holds. ``_complete_claim``
# used to lock the StorageCleanupTask row *first*, then (only in the
# asset-bearing, non-failed branch) go on to lock User and then VideoAsset --
# a reversed Task -> User -> Asset order. These tests pin the corrected
# behavior: a nonlocking preview identifies the task/asset, User is locked,
# then Asset, and only as the final, authoritative step is Task re-locked
# (and its lease revalidated) before any accounting is mutated.


def test_complete_claim_locks_user_and_asset_before_final_task_relock(
    db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    """Structural regression for the lock-order fix.

    SQLite neither blocks on ``FOR UPDATE`` nor renders it in compiled SQL,
    so genuine cross-session deadlocking cannot be demonstrated here.
    Instead this traces the exact sequence of ORM selects (and their
    ``FOR UPDATE`` flag, and engine commits) issued by a single
    ``_complete_claim`` call and asserts:

    * the User row is locked, then the VideoAsset row is locked, and only
      *after* both are the final, authoritative (lease-revalidating) lock
      of the StorageCleanupTask row taken; and
    * if any Task lock preceded the User lock, it must have been released
      (via a commit) before User was locked -- Task may never be held
      while a User lock is requested.
    """
    from app.models.project import Project
    from app.models.video import VideoAsset
    from app.services.storage_cleanup import _claim_task_for_processing, _complete_claim
    from tests.conftest import create_user

    owner = create_user(db_session, email="lock-order@example.com", password="Passw0rd!123")
    project = Project(owner_id=owner.id, name="Lock order")
    db_session.add(project)
    db_session.flush()
    video_asset = VideoAsset(
        project_id=project.id,
        owner_id=owner.id,
        object_key="projects/x/source/lock-order.mp4",
        original_filename="lock-order.mp4",
        content_type="video/mp4",
        declared_size_bytes=1000,
        declared_duration_seconds=5.0,
        status=VideoAssetStatus.CLEANUP_PENDING,
        upload_id="upload-1",
        part_count=1,
        storage_counted_bytes=1000,
    )
    db_session.add(video_asset)
    db_session.flush()
    db_session.commit()
    db_session.refresh(video_asset)

    object_key = video_asset.object_key
    fake_storage.objects[object_key] = ObjectMetadata(size_bytes=1000, content_type="video/mp4")
    task = _create_delete_task(db_session, object_key=object_key, video_asset_id=video_asset.id)
    task_id = task.id
    claim = _claim_task_for_processing(db_session, task_id)
    assert claim is not None
    _task, lease_token = claim
    fake_storage.delete_object(object_key=object_key)

    events: list[tuple[str, str, bool]] = []

    def _capture_orm_execute(orm_execute_state):
        if not orm_execute_state.is_select:
            return
        try:
            froms = [t.name for t in orm_execute_state.statement.get_final_froms()]
        except Exception:  # pragma: no cover - defensive, statement shape only
            froms = []
        locking = getattr(orm_execute_state.statement, "_for_update_arg", None) is not None
        for table in froms:
            events.append(("select", table, locking))

    def _capture_commit(conn) -> None:
        events.append(("commit", "", False))

    engine = db_session.get_bind()
    event.listen(db_session, "do_orm_execute", _capture_orm_execute)
    event.listen(engine, "commit", _capture_commit)
    try:
        _complete_claim(db_session, task_id, lease_token, failed=False)
    finally:
        event.remove(db_session, "do_orm_execute", _capture_orm_execute)
        event.remove(engine, "commit", _capture_commit)

    task_lock_positions = [
        i for i, e in enumerate(events) if e[0] == "select" and e[1] == "storage_cleanup_tasks" and e[2]
    ]
    user_lock_positions = [
        i for i, e in enumerate(events) if e[0] == "select" and e[1] == "users" and e[2]
    ]
    asset_lock_positions = [
        i for i, e in enumerate(events) if e[0] == "select" and e[1] == "video_assets" and e[2]
    ]
    commit_positions = [i for i, e in enumerate(events) if e[0] == "commit"]

    assert task_lock_positions, "expected a locking StorageCleanupTask select"
    assert user_lock_positions, "completion must lock the owning User"
    assert asset_lock_positions, "completion must lock the VideoAsset"

    first_user = user_lock_positions[0]
    first_asset_after_user = next(p for p in asset_lock_positions if p > first_user)
    final_task_lock = task_lock_positions[-1]

    earlier_task_locks = [p for p in task_lock_positions if p < first_user]
    for task_lock in earlier_task_locks:
        assert any(task_lock < c < first_user for c in commit_positions), (
            "a Task lock preceded the User lock without an intervening "
            "commit -- Task must never be held while waiting for User"
        )

    assert first_user < first_asset_after_user < final_task_lock, (
        "the final, lease-revalidating Task lock must come after both "
        "User and Asset are already locked (global User -> Asset -> Task "
        "order)"
    )


def test_complete_claim_observes_fresh_state_across_two_sessions(
    session_factory, fake_storage: FakeObjectStorage
) -> None:
    """Two independent Sessions: one completes a DELETE_OBJECT task's
    accounting release while another session concurrently holds a stale
    (pre-release) in-memory copy of the same VideoAsset. The completing
    session must observe the true committed state through its own
    User -> Asset -> Task locking (with ``populate_existing`` on the
    Asset), release accounting exactly once, and never drive usage
    negative -- regardless of what a stale sibling session has cached."""
    from app.models.enums import QuotaLedgerEventType
    from app.models.project import Project
    from app.models.video import VideoAsset
    from app.services import quota as quota_service
    from app.services.storage_cleanup import _claim_task_for_processing, _complete_claim
    from tests.conftest import create_user

    session_setup = session_factory()
    try:
        owner = create_user(session_setup, email="two-session-complete@example.com", password="Passw0rd!123")
        project = Project(owner_id=owner.id, name="Two session complete")
        session_setup.add(project)
        session_setup.flush()
        video_asset = VideoAsset(
            project_id=project.id,
            owner_id=owner.id,
            object_key="projects/x/source/two-session-complete.mp4",
            original_filename="two-session-complete.mp4",
            content_type="video/mp4",
            declared_size_bytes=1000,
            declared_duration_seconds=5.0,
            status=VideoAssetStatus.CLEANUP_PENDING,
            upload_id="upload-1",
            part_count=1,
            storage_counted_bytes=1000,
        )
        session_setup.add(video_asset)
        session_setup.flush()
        quota_service.record_ledger_event(
            session_setup,
            user_id=owner.id,
            event_type=QuotaLedgerEventType.UPLOAD_FINALIZED,
            video_asset_id=video_asset.id,
            bytes_delta=1000,
        )
        object_key = video_asset.object_key
        fake_storage.objects[object_key] = ObjectMetadata(size_bytes=1000, content_type="video/mp4")
        task = _create_delete_task(session_setup, object_key=object_key, video_asset_id=video_asset.id)
        task_id = task.id
        owner_id = owner.id
        video_asset_id = video_asset.id
        session_setup.commit()
    finally:
        session_setup.close()

    # Session A: a sibling worker session that preloads the VideoAsset into
    # its own identity map *before* the real completion runs elsewhere, so
    # its cached copy is stale by the time it later looks at the row again.
    session_a = session_factory()
    # Session B: performs the actual claim + delete + completion.
    session_b = session_factory()
    try:
        stale_view = session_a.get(VideoAsset, video_asset_id)
        assert stale_view is not None
        assert stale_view.storage_counted_bytes == 1000

        claim = _claim_task_for_processing(session_b, task_id)
        assert claim is not None
        _task_b, lease_token = claim
        fake_storage.delete_object(object_key=object_key)
        _complete_claim(session_b, task_id, lease_token, failed=False)

        session_b.commit()

        session_b.refresh(_task_b)
        assert _task_b.status == StorageCleanupStatus.COMPLETED
        completed_asset = session_b.get(VideoAsset, video_asset_id)
        assert completed_asset is not None
        assert completed_asset.storage_counted_bytes == 0
        assert quota_service.storage_bytes_used(session_b, owner_id) == 0

        # Session A's stale in-memory copy must not be what any further
        # release logic in session B relies on -- session B's own fresh,
        # populate_existing reselect is what determined the outcome above.
        # Confirm usage never went negative and the release happened
        # exactly once by re-running completion with the same (now
        # superseded) lease: a pure no-op.
        _complete_claim(session_b, task_id, lease_token, failed=False)
        session_b.commit()
        assert quota_service.storage_bytes_used(session_b, owner_id) == 0
    finally:
        session_a.close()
        session_b.close()
