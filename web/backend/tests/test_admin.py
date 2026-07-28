from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import JobStatus, UserRole
from app.models.job import AnalysisJob, ExportJob
from app.models.project import Project
from app.models.video import VideoAsset
from tests.conftest import auth_headers, create_user, login


def test_admin_endpoints_require_admin_role(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="regular@example.com", password="password123")
    token = login(client, email="regular@example.com", password="password123")

    response = client.get("/api/v1/admin/users", headers=auth_headers(token))
    assert response.status_code == 403


def test_admin_endpoints_require_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/admin/users")
    assert response.status_code == 401


def test_admin_can_list_users_and_projects(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="regular@example.com", password="password123")
    create_user(db_session, email="admin@example.com", password="password123", role=UserRole.ADMIN)
    admin_token = login(client, email="admin@example.com", password="password123")

    regular_token = login(client, email="regular@example.com", password="password123")
    client.post("/api/v1/projects", json={"name": "Match"}, headers=auth_headers(regular_token))

    users_response = client.get("/api/v1/admin/users", headers=auth_headers(admin_token))
    assert users_response.status_code == 200
    emails = {u["email"] for u in users_response.json()}
    assert {"regular@example.com", "admin@example.com"} <= emails
    # Password hashes must never leak through the admin API.
    assert all("password_hash" not in u for u in users_response.json())

    projects_response = client.get("/api/v1/admin/projects", headers=auth_headers(admin_token))
    assert projects_response.status_code == 200
    assert len(projects_response.json()) == 1


def test_admin_can_list_analysis_jobs_by_status(client: TestClient, db_session: Session) -> None:
    owner = create_user(db_session, email="owner@example.com", password="password123")
    create_user(db_session, email="admin@example.com", password="password123", role=UserRole.ADMIN)
    admin_token = login(client, email="admin@example.com", password="password123")

    project = Project(owner_id=owner.id, name="Match")
    db_session.add(project)
    db_session.flush()
    video_asset = VideoAsset(
        project_id=project.id,
        owner_id=owner.id,
        object_key="projects/x/source/y.mp4",
        original_filename="match.mp4",
        content_type="video/mp4",
        declared_size_bytes=1024,
        declared_duration_seconds=600.0,
        upload_id="upload-1",
        part_count=1,
    )
    db_session.add(video_asset)
    db_session.flush()
    job = AnalysisJob(
        project_id=project.id, video_asset_id=video_asset.id, owner_id=owner.id, status=JobStatus.QUEUED
    )
    db_session.add(job)
    db_session.commit()

    response = client.get(
        "/api/v1/admin/analysis-jobs", params={"status": "queued"}, headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == str(job.id)

    empty_response = client.get(
        "/api/v1/admin/analysis-jobs", params={"status": "failed"}, headers=auth_headers(admin_token)
    )
    assert empty_response.json() == []


def test_admin_failures_endpoint_includes_admin_only_diagnostics(
    client: TestClient, db_session: Session
) -> None:
    owner = create_user(db_session, email="owner@example.com", password="password123")
    create_user(db_session, email="admin@example.com", password="password123", role=UserRole.ADMIN)
    admin_token = login(client, email="admin@example.com", password="password123")

    project = Project(owner_id=owner.id, name="Match")
    db_session.add(project)
    db_session.flush()
    video_asset = VideoAsset(
        project_id=project.id,
        owner_id=owner.id,
        object_key="projects/x/source/y.mp4",
        original_filename="match.mp4",
        content_type="video/mp4",
        declared_size_bytes=1024,
        declared_duration_seconds=600.0,
        upload_id="upload-1",
        part_count=1,
    )
    db_session.add(video_asset)
    db_session.flush()
    failed_job = AnalysisJob(
        project_id=project.id,
        video_asset_id=video_asset.id,
        owner_id=owner.id,
        status=JobStatus.FAILED,
        failure_summary="Engine crashed",
        failure_detail="Traceback (most recent call last): ...",
    )
    failed_export = ExportJob(
        project_id=project.id,
        owner_id=owner.id,
        status=JobStatus.FAILED,
        failure_summary="ffmpeg failed",
        failure_detail="exit code 1: ...",
    )
    db_session.add_all([failed_job, failed_export])
    db_session.commit()

    response = client.get("/api/v1/admin/failures", headers=auth_headers(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    job_types = {item["job_type"] for item in body}
    assert job_types == {"analysis", "export"}
    assert all(item["failure_detail"] is not None for item in body)


def test_admin_endpoints_have_no_mutation_routes(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="admin@example.com", password="password123", role=UserRole.ADMIN)
    admin_token = login(client, email="admin@example.com", password="password123")

    response = client.post(
        "/api/v1/admin/users",
        json={"email": "new@example.com"},
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 405
