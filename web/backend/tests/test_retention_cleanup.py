from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.enums import JobStatus, VideoAssetStatus
from app.models.job import ExportJob
from app.models.project import Project
from app.models.video import VideoAsset
from app.services.retention import run_retention_cleanup
from tests.conftest import create_user
from tests.fakes import FakeObjectStorage


def test_retention_cleanup_retries_source_and_export_deletion_idempotently(
    db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    owner = create_user(
        db_session, email="owner@example.com", password="Test-password-123"
    )
    project = Project(owner_id=owner.id, name="Match")
    db_session.add(project)
    db_session.flush()
    source_key = f"projects/{project.id}/source/match.mp4"
    export_key = f"projects/{project.id}/exports/highlights.mp4"
    asset = VideoAsset(
        project_id=project.id,
        owner_id=owner.id,
        object_key=source_key,
        original_filename="match.mp4",
        content_type="video/mp4",
        declared_size_bytes=5,
        actual_size_bytes=5,
        declared_duration_seconds=10,
        status=VideoAssetStatus.UPLOADED,
        upload_id="upload",
        part_count=1,
        storage_counted_bytes=5,
        retention_expires_at=utcnow() - timedelta(seconds=1),
    )
    export = ExportJob(
        project_id=project.id,
        owner_id=owner.id,
        status=JobStatus.SUCCEEDED,
        output_object_key=export_key,
        output_expires_at=utcnow() - timedelta(seconds=1),
        selection_snapshot=[],
    )
    db_session.add_all([asset, export])
    db_session.commit()
    fake_storage.put_bytes(object_key=source_key, data=b"video", content_type="video/mp4")
    fake_storage.put_bytes(object_key=export_key, data=b"export", content_type="video/mp4")
    fake_storage.fail_next_deletes = 1

    run_retention_cleanup(db_session, fake_storage, now=utcnow())
    db_session.expire_all()
    assert db_session.get(VideoAsset, asset.id).storage_counted_bytes == 5

    run_retention_cleanup(db_session, fake_storage, now=utcnow() + timedelta(minutes=10))
    db_session.expire_all()
    assert db_session.get(VideoAsset, asset.id).storage_counted_bytes == 0
    assert db_session.get(ExportJob, export.id).output_object_key is None
