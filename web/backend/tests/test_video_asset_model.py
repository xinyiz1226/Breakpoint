"""Model-level contract coverage for the worker-authoritative duration cap.

The nullable ``duration_seconds``/``duration_status`` pair is never set by
this layer — it is reserved for a future worker's ffprobe result (see
``VideoAsset`` docstring). This is distinct from ``declared_duration_seconds``,
the required, client-declared field validated and used for quota reservation
at upload initiation (covered in ``tests/test_uploads.py``). These tests pin
the DB-level contract a future worker will rely on: both authoritative
fields default to NULL and accept the documented ``VideoDurationStatus``
values when a worker eventually sets them.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.enums import VideoAssetStatus, VideoDurationStatus
from app.models.project import Project
from app.models.user import User
from app.models.video import VideoAsset
from app.security import hash_password


def _make_owner(db: Session) -> User:
    owner = User(email="owner@example.com", password_hash=hash_password("password123"))
    db.add(owner)
    db.commit()
    db.refresh(owner)
    return owner


def _make_project(db: Session, owner: User) -> Project:
    project = Project(owner_id=owner.id, name="Match")
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def test_duration_fields_default_to_null(db_session: Session) -> None:
    owner = _make_owner(db_session)
    project = _make_project(db_session, owner)

    video_asset = VideoAsset(
        project_id=project.id,
        owner_id=owner.id,
        object_key=f"videos/{uuid.uuid4()}/source.mp4",
        original_filename="source.mp4",
        content_type="video/mp4",
        declared_size_bytes=1024,
        declared_duration_seconds=600.0,
        upload_id="upload-1",
        part_count=1,
        status=VideoAssetStatus.UPLOAD_INITIATED,
    )
    db_session.add(video_asset)
    db_session.commit()
    db_session.refresh(video_asset)

    assert video_asset.duration_seconds is None
    assert video_asset.duration_status is None


def test_duration_status_persists_worker_verdicts(db_session: Session) -> None:
    """Simulates what a future worker would write; this layer never does."""
    owner = _make_owner(db_session)
    project = _make_project(db_session, owner)

    video_asset = VideoAsset(
        project_id=project.id,
        owner_id=owner.id,
        object_key=f"videos/{uuid.uuid4()}/source.mp4",
        original_filename="source.mp4",
        content_type="video/mp4",
        declared_size_bytes=1024,
        declared_duration_seconds=12000.0,
        upload_id="upload-1",
        part_count=1,
        status=VideoAssetStatus.UPLOAD_INITIATED,
        duration_seconds=12000.0,
        duration_status=VideoDurationStatus.EXCEEDED,
    )
    db_session.add(video_asset)
    db_session.commit()
    db_session.refresh(video_asset)

    assert video_asset.duration_seconds == 12000.0
    assert video_asset.duration_status == VideoDurationStatus.EXCEEDED
