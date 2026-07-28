"""Direct service-contract tests for the worker-facing analysis-reservation
reconciliation seam (``app.services.analysis_reservation``).

This is the explicit "next layer" public service seam: a future analysis
worker calls it after ffprobing a finalized asset's authoritative duration,
before running analysis. These tests call the service function directly
(not through any HTTP endpoint) with a hand-built VideoAsset/AnalysisJob,
since there is no worker layer/router in this codebase yet.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.enums import (
    JobStatus,
    QuotaLedgerEventType,
    VideoAssetStatus,
    VideoDurationStatus,
)
from app.models.job import AnalysisJob
from app.models.project import Project
from app.models.quota import QuotaLedgerEntry
from app.models.video import VideoAsset
from app.services import quota as quota_service
from app.services.analysis_reservation import apply_authoritative_duration
from tests.conftest import create_user

SETTINGS = Settings(
    environment="test",
    jwt_secret_key="test-jwt-secret-key-at-least-32-bytes-long",
    default_monthly_analysis_seconds=3600,
    max_video_duration_seconds=1800,
)


def _create_asset_with_job(
    db: Session, *, declared_duration: float, owner=None
) -> tuple[VideoAsset, AnalysisJob]:
    if owner is None:
        owner = create_user(
            db, email=f"{uuid.uuid4().hex}@example.com", password="valid-test-password"
        )
    project = Project(owner_id=owner.id, name="Match")
    db.add(project)
    db.flush()
    video_asset = VideoAsset(
        project_id=project.id,
        owner_id=owner.id,
        object_key=f"projects/{project.id}/source/{uuid.uuid4()}.mp4",
        original_filename="match.mp4",
        content_type="video/mp4",
        declared_size_bytes=1024,
        declared_duration_seconds=declared_duration,
        status=VideoAssetStatus.UPLOADED,
        upload_id="upload-1",
        part_count=1,
        analysis_reserved_seconds=declared_duration,
    )
    db.add(video_asset)
    db.flush()
    quota_service.record_ledger_event(
        db,
        user_id=owner.id,
        event_type=QuotaLedgerEventType.ANALYSIS_RESERVED,
        video_asset_id=video_asset.id,
        seconds_delta=declared_duration,
    )
    job = AnalysisJob(
        project_id=project.id,
        video_asset_id=video_asset.id,
        owner_id=owner.id,
        status=JobStatus.QUEUED,
    )
    db.add(job)
    db.commit()
    db.refresh(video_asset)
    db.refresh(job)
    return video_asset, job


def _ledger_entries(db: Session, video_asset_id: uuid.UUID) -> list[QuotaLedgerEntry]:
    return list(
        db.execute(
            select(QuotaLedgerEntry)
            .where(QuotaLedgerEntry.video_asset_id == video_asset_id)
            .order_by(QuotaLedgerEntry.created_at.asc())
        ).scalars()
    )


def test_grows_reservation_when_authoritative_duration_is_larger(db_session: Session) -> None:
    video_asset, job = _create_asset_with_job(db_session, declared_duration=100.0)

    result = apply_authoritative_duration(
        db_session,
        video_asset_id=video_asset.id,
        analysis_job_id=job.id,
        authoritative_duration_seconds=150.0,
        settings=SETTINGS,
    )

    assert result.status == JobStatus.QUEUED
    db_session.refresh(video_asset)
    assert video_asset.analysis_reserved_seconds == 150.0
    assert video_asset.duration_seconds == 150.0
    assert video_asset.duration_status == VideoDurationStatus.WITHIN_LIMIT

    entries = _ledger_entries(db_session, video_asset.id)
    # Initial reservation (100) + release (-100) + reserve (+150).
    assert [e.event_type for e in entries] == [
        QuotaLedgerEventType.ANALYSIS_RESERVED,
        QuotaLedgerEventType.ANALYSIS_RESERVATION_RELEASED,
        QuotaLedgerEventType.ANALYSIS_RESERVED,
    ]
    assert quota_service.monthly_analysis_seconds_used(db_session, video_asset.owner_id) == 150.0


def test_shrinks_reservation_when_authoritative_duration_is_smaller(db_session: Session) -> None:
    video_asset, job = _create_asset_with_job(db_session, declared_duration=200.0)

    apply_authoritative_duration(
        db_session,
        video_asset_id=video_asset.id,
        analysis_job_id=job.id,
        authoritative_duration_seconds=80.0,
        settings=SETTINGS,
    )

    db_session.refresh(video_asset)
    assert video_asset.analysis_reserved_seconds == 80.0
    assert quota_service.monthly_analysis_seconds_used(db_session, video_asset.owner_id) == 80.0


def test_duration_exceeding_cap_fails_job_and_releases_reservation(db_session: Session) -> None:
    video_asset, job = _create_asset_with_job(db_session, declared_duration=100.0)

    result = apply_authoritative_duration(
        db_session,
        video_asset_id=video_asset.id,
        analysis_job_id=job.id,
        authoritative_duration_seconds=SETTINGS.max_video_duration_seconds + 1,
        settings=SETTINGS,
    )

    assert result.status == JobStatus.FAILED
    assert result.failure_summary is not None
    db_session.refresh(video_asset)
    assert video_asset.duration_status == VideoDurationStatus.EXCEEDED
    assert video_asset.analysis_reserved_seconds == 0.0
    assert quota_service.monthly_analysis_seconds_used(db_session, video_asset.owner_id) == 0.0


def test_resized_reservation_exceeding_monthly_quota_fails_job_and_releases_reservation(
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="quota@example.com", password="valid-test-password")
    # Consume almost all of the monthly budget with an unrelated reservation.
    _create_asset_with_job(db_session, declared_duration=3500.0, owner=owner)

    video_asset, job = _create_asset_with_job(db_session, declared_duration=50.0, owner=owner)

    result = apply_authoritative_duration(
        db_session,
        video_asset_id=video_asset.id,
        analysis_job_id=job.id,
        authoritative_duration_seconds=200.0,  # within per-video cap, but 3500 + 200 > 3600
        settings=SETTINGS,
    )

    assert result.status == JobStatus.FAILED
    assert result.failure_summary is not None
    db_session.refresh(video_asset)
    assert video_asset.duration_status == VideoDurationStatus.WITHIN_LIMIT
    assert video_asset.analysis_reserved_seconds == 0.0
    # Only the unrelated 3500s reservation remains booked.
    assert quota_service.monthly_analysis_seconds_used(db_session, owner.id) == 3500.0


def test_replaying_the_same_authoritative_duration_is_idempotent(db_session: Session) -> None:
    video_asset, job = _create_asset_with_job(db_session, declared_duration=100.0)

    apply_authoritative_duration(
        db_session,
        video_asset_id=video_asset.id,
        analysis_job_id=job.id,
        authoritative_duration_seconds=150.0,
        settings=SETTINGS,
    )
    entries_after_first = _ledger_entries(db_session, video_asset.id)

    result = apply_authoritative_duration(
        db_session,
        video_asset_id=video_asset.id,
        analysis_job_id=job.id,
        authoritative_duration_seconds=150.0,
        settings=SETTINGS,
    )

    entries_after_second = _ledger_entries(db_session, video_asset.id)
    assert len(entries_after_second) == len(entries_after_first)
    db_session.refresh(video_asset)
    assert video_asset.analysis_reserved_seconds == 150.0
    assert result.status == JobStatus.QUEUED
