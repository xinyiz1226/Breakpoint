from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.enums import JobStatus, VideoAssetStatus
from app.models.job import AnalysisJob, ExportJob
from app.models.project import Project
from app.models.rally import Rally, RallyEdit
from app.models.video import VideoAsset
from app.services.job_events import iter_job_events
from tests.conftest import auth_headers, create_user, login


def _project_with_rallies(db: Session, *, email: str) -> tuple[Project, AnalysisJob]:
    owner = create_user(db, email=email, password="Test-password-123")
    project = Project(owner_id=owner.id, name="Match")
    db.add(project)
    db.flush()
    asset = VideoAsset(
        project_id=project.id,
        owner_id=owner.id,
        object_key=f"projects/{project.id}/source/match.mp4",
        original_filename="match.mp4",
        content_type="video/mp4",
        declared_size_bytes=10,
        actual_size_bytes=10,
        declared_duration_seconds=100,
        duration_seconds=100,
        retention_expires_at=utcnow() + timedelta(days=1),
        status=VideoAssetStatus.UPLOADED,
        upload_id="upload",
        part_count=1,
    )
    db.add(asset)
    db.flush()
    job = AnalysisJob(
        project_id=project.id,
        video_asset_id=asset.id,
        owner_id=owner.id,
        status=JobStatus.SUCCEEDED,
        progress=1,
        event_version=4,
    )
    db.add(job)
    db.flush()
    first = Rally(
        analysis_job_id=job.id,
        source_index=1,
        start=10,
        end=20,
        score=2,
        features={},
        report_version="2",
    )
    second = Rally(
        analysis_job_id=job.id,
        source_index=2,
        start=30,
        end=40,
        score=1,
        features={},
        report_version="2",
    )
    db.add_all([first, second])
    db.flush()
    db.add_all(
        [
            RallyEdit(rally_id=first.id, included=True, adjusted_start=11, adjusted_end=19),
            RallyEdit(rally_id=second.id, included=False),
        ]
    )
    db.commit()
    return project, job


def test_export_creation_persists_selection_snapshot_before_enqueue(
    client: TestClient, db_session: Session
) -> None:
    project, _ = _project_with_rallies(db_session, email="owner@example.com")
    token = login(client, email="owner@example.com", password="Test-password-123")

    response = client.post(
        f"/api/v1/projects/{project.id}/exports",
        headers=auth_headers(token),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["selection_snapshot"] == [
        {"rally_id": body["selection_snapshot"][0]["rally_id"], "start": 11.0, "end": 19.0}
    ]


def test_export_creation_rejects_a_second_active_export(
    client: TestClient, db_session: Session
) -> None:
    project, _ = _project_with_rallies(
        db_session, email="active-export-owner@example.com"
    )
    token = login(
        client,
        email="active-export-owner@example.com",
        password="Test-password-123",
    )

    first = client.post(
        f"/api/v1/projects/{project.id}/exports",
        headers=auth_headers(token),
    )
    second = client.post(
        f"/api/v1/projects/{project.id}/exports",
        headers=auth_headers(token),
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert len(
        db_session.execute(
            select(ExportJob).where(ExportJob.project_id == project.id)
        ).scalars().all()
    ) == 1


def test_cancel_is_owner_scoped_and_hides_failure_detail(
    client: TestClient, db_session: Session
) -> None:
    project, job = _project_with_rallies(db_session, email="owner@example.com")
    job.status = JobStatus.RUNNING
    job.failure_detail = "private stderr"
    db_session.commit()
    create_user(
        db_session, email="other@example.com", password="Test-password-123"
    )
    other_token = login(
        client, email="other@example.com", password="Test-password-123"
    )
    owner_token = login(
        client, email="owner@example.com", password="Test-password-123"
    )

    denied = client.post(
        f"/api/v1/projects/{project.id}/analysis/cancel",
        headers=auth_headers(other_token),
    )
    assert denied.status_code == 404

    response = client.post(
        f"/api/v1/projects/{project.id}/analysis/cancel",
        headers=auth_headers(owner_token),
    )
    assert response.status_code == 200
    assert "failure_detail" not in response.json()
    db_session.refresh(job)
    assert job.cancel_requested_at is not None


def test_sse_reconnect_uses_persisted_monotonic_version_and_short_sessions(
    session_factory, db_session: Session
) -> None:
    project, job = _project_with_rallies(db_session, email="owner@example.com")
    sessions_opened = 0

    def tracked_factory():
        nonlocal sessions_opened
        sessions_opened += 1
        return session_factory()

    events = iter_job_events(
        tracked_factory,
        job_kind="analysis",
        job_id=job.id,
        owner_id=project.owner_id,
        last_event_id=3,
        poll_seconds=0,
        max_events=1,
    )
    event = next(events)
    assert event.startswith("id: 4\n")
    assert '"status":"succeeded"' in event
    assert sessions_opened == 1

    no_events = list(
        iter_job_events(
            tracked_factory,
            job_kind="analysis",
            job_id=job.id,
            owner_id=project.owner_id,
            last_event_id=4,
            poll_seconds=0,
            max_events=0,
        )
    )
    assert no_events == []

    assert list(
        iter_job_events(
            tracked_factory,
            job_kind="analysis",
            job_id=job.id,
            owner_id=uuid.uuid4(),
            last_event_id=0,
            poll_seconds=0,
            max_events=1,
        )
    ) == []


def test_failed_analysis_retry_rebooks_authoritative_duration(
    client: TestClient, db_session: Session
) -> None:
    project, job = _project_with_rallies(db_session, email="retry@example.com")
    job.status = JobStatus.FAILED
    job.video_asset.analysis_reserved_seconds = 0
    job.video_asset.duration_seconds = 100
    db_session.commit()
    token = login(client, email="retry@example.com", password="Test-password-123")

    response = client.post(
        f"/api/v1/projects/{project.id}/analysis/retry",
        headers=auth_headers(token),
    )

    assert response.status_code == 200, response.text
    db_session.expire_all()
    assert db_session.get(AnalysisJob, job.id).status == JobStatus.QUEUED
    assert db_session.get(AnalysisJob, job.id).video_asset.analysis_reserved_seconds == 100


def test_sse_endpoint_requires_owner_auth(
    client: TestClient, db_session: Session
) -> None:
    project, _ = _project_with_rallies(db_session, email="stream-owner@example.com")
    create_user(
        db_session, email="stream-other@example.com", password="Test-password-123"
    )
    other_token = login(
        client, email="stream-other@example.com", password="Test-password-123"
    )

    unauthenticated = client.get(
        f"/api/v1/projects/{project.id}/analysis/events"
    )
    assert unauthenticated.status_code == 401

    wrong_owner = client.get(
        f"/api/v1/projects/{project.id}/analysis/events",
        headers=auth_headers(other_token),
    )
    assert wrong_owner.status_code == 404


def test_expired_export_cannot_issue_a_new_signed_url(
    client: TestClient, db_session: Session
) -> None:
    project, analysis = _project_with_rallies(
        db_session, email="expired-export@example.com"
    )
    export = ExportJob(
        project_id=project.id,
        owner_id=project.owner_id,
        status=JobStatus.SUCCEEDED,
        selection_snapshot=[],
        output_object_key=f"projects/{project.id}/exports/expired.mp4",
        output_expires_at=utcnow() - timedelta(seconds=1),
    )
    db_session.add(export)
    db_session.commit()
    token = login(
        client,
        email="expired-export@example.com",
        password="Test-password-123",
    )

    response = client.get(
        f"/api/v1/projects/{project.id}/exports/{export.id}/signed-url",
        headers=auth_headers(token),
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("asset_status", "expires_at"),
    [
        (VideoAssetStatus.UPLOADED, utcnow() - timedelta(seconds=1)),
        (VideoAssetStatus.CLEANUP_PENDING, utcnow() + timedelta(days=1)),
    ],
)
def test_export_creation_requires_live_unexpired_source(
    asset_status: VideoAssetStatus,
    expires_at,
    client: TestClient,
    db_session: Session,
) -> None:
    project, analysis = _project_with_rallies(
        db_session, email=f"{uuid.uuid4().hex}@example.com"
    )
    analysis.video_asset.status = asset_status
    analysis.video_asset.retention_expires_at = expires_at
    db_session.commit()
    token = login(
        client,
        email=analysis.project.owner.email,
        password="Test-password-123",
    )

    response = client.post(
        f"/api/v1/projects/{project.id}/exports",
        headers=auth_headers(token),
    )

    assert response.status_code == 409
    assert db_session.execute(
        select(ExportJob).where(ExportJob.project_id == project.id)
    ).first() is None


def test_export_retry_requires_live_unexpired_source(
    client: TestClient, db_session: Session
) -> None:
    project, analysis = _project_with_rallies(
        db_session, email="expired-retry@example.com"
    )
    analysis.video_asset.retention_expires_at = utcnow() - timedelta(seconds=1)
    export = ExportJob(
        project_id=project.id,
        owner_id=project.owner_id,
        status=JobStatus.FAILED,
        selection_snapshot=[],
    )
    db_session.add(export)
    db_session.commit()
    token = login(
        client,
        email="expired-retry@example.com",
        password="Test-password-123",
    )

    response = client.post(
        f"/api/v1/projects/{project.id}/exports/{export.id}/retry",
        headers=auth_headers(token),
    )

    assert response.status_code == 409
    db_session.refresh(export)
    assert export.status == JobStatus.FAILED
