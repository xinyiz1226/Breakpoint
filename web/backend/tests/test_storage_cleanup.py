"""Service-seam tests for the durable storage-cleanup outbox.

``claim_and_process`` is the "worker" that actually performs a durable
``StorageCleanupTask``'s S3 side effect. These tests exercise it directly
against the in-memory ``FakeObjectStorage`` rather than through an API
endpoint, since the cleanup task itself -- not any particular caller -- is
the seam under test.
"""

from __future__ import annotations

import uuid

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

    claim_and_process(db_session, task, fake_storage)

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

    claim_and_process(db_session, task, fake_storage)

    assert task.status == StorageCleanupStatus.FAILED
    assert task.attempts == 1
    assert task.last_error is not None
    assert task.completed_at is None
    # The object was never actually deleted -- no untracked/orphaned object,
    # and the durable task is still there to retry.
    assert object_key in fake_storage.objects

    # A later retry (same task, now that storage recovers) succeeds and
    # completes it -- attempts accumulate rather than resetting.
    claim_and_process(db_session, task, fake_storage)
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

    claim_and_process(db_session, task, fake_storage)

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

    claim_and_process(db_session, task, fake_storage)

    assert task.status == StorageCleanupStatus.FAILED
    db_session.refresh(video_asset)
    assert video_asset.storage_counted_bytes == 1000
    assert quota_service.storage_bytes_used(db_session, owner.id) == 1000

    # Retry succeeds now that storage recovers: only now is the balance
    # released.
    claim_and_process(db_session, task, fake_storage)

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
