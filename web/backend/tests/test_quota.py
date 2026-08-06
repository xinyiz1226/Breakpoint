from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.storage import ObjectMetadata
from tests.conftest import auth_headers, create_user, login
from tests.fakes import FakeObjectStorage

CONTENT_TYPE = "video/mp4"
DECLARED_SIZE = 10 * 1024 * 1024
DECLARED_DURATION = 600.0  # 10 minutes


def _create_and_finalize_video(
    client: TestClient, token: str, project_id: str, fake_storage: FakeObjectStorage
) -> None:
    initiate = client.post(
        f"/api/v1/projects/{project_id}/uploads",
        json={
            "filename": "match.mp4",
            "content_type": CONTENT_TYPE,
            "size_bytes": DECLARED_SIZE,
            "duration_seconds": DECLARED_DURATION,
            "part_count": 1,
        },
        headers=auth_headers(token),
    ).json()
    fake_storage.objects[initiate["object_key"]] = ObjectMetadata(
        size_bytes=DECLARED_SIZE, content_type=CONTENT_TYPE
    )
    finalize = client.post(
        f"/api/v1/projects/{project_id}/uploads/{initiate['video_asset_id']}/finalize",
        json={"idempotency_key": "key-1", "parts": [{"part_number": 1, "etag": "etag-1"}]},
        headers=auth_headers(token),
    )
    assert finalize.status_code == 200, finalize.text


def test_quota_me_returns_configured_defaults(
    client: TestClient, db_session: Session, test_settings
) -> None:
    create_user(db_session, email="owner@example.com", password="password123")
    token = login(client, email="owner@example.com", password="password123")

    response = client.get("/api/v1/quota/me", headers=auth_headers(token))
    assert response.status_code == 200
    body = response.json()
    assert body["monthly_analysis_seconds_limit"] == test_settings.default_monthly_analysis_seconds
    assert body["monthly_analysis_seconds_used"] == 0
    assert body["max_active_analysis_jobs"] == test_settings.default_max_active_analysis_jobs
    assert body["active_analysis_job_count"] == 0


def test_active_job_count_reflects_queued_job_after_finalize(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    create_user(db_session, email="owner@example.com", password="password123")
    token = login(client, email="owner@example.com", password="password123")
    project_id = client.post(
        "/api/v1/projects", json={"name": "Match"}, headers=auth_headers(token)
    ).json()["id"]

    _create_and_finalize_video(client, token, project_id, fake_storage)

    response = client.get("/api/v1/quota/me", headers=auth_headers(token))
    assert response.json()["active_analysis_job_count"] == 1


def test_second_project_upload_blocked_by_active_job_quota(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    # test_settings.default_max_active_analysis_jobs == 1
    create_user(db_session, email="owner@example.com", password="password123")
    token = login(client, email="owner@example.com", password="password123")

    first_project_id = client.post(
        "/api/v1/projects", json={"name": "Match 1"}, headers=auth_headers(token)
    ).json()["id"]
    _create_and_finalize_video(client, token, first_project_id, fake_storage)

    second_project_id = client.post(
        "/api/v1/projects", json={"name": "Match 2"}, headers=auth_headers(token)
    ).json()["id"]
    second_initiate = client.post(
        f"/api/v1/projects/{second_project_id}/uploads",
        json={
            "filename": "match2.mp4",
            "content_type": CONTENT_TYPE,
            "size_bytes": DECLARED_SIZE,
            "duration_seconds": DECLARED_DURATION,
            "part_count": 1,
        },
        headers=auth_headers(token),
    )
    assert second_initiate.status_code == 403


def test_per_user_quota_override_raises_limit(client: TestClient, db_session: Session) -> None:
    user = create_user(db_session, email="vip@example.com", password="password123")
    user.quota_monthly_analysis_seconds_override = 72000
    user.quota_max_active_analysis_jobs_override = 5
    db_session.commit()

    token = login(client, email="vip@example.com", password="password123")
    response = client.get("/api/v1/quota/me", headers=auth_headers(token))
    body = response.json()
    assert body["monthly_analysis_seconds_limit"] == 72000
    assert body["max_active_analysis_jobs"] == 5


def test_zero_quota_override_is_respected_and_not_treated_as_default(
    client: TestClient, db_session: Session, test_settings
) -> None:
    # A `0` override must mean "no quota at all", distinct from `None`
    # ("use the configured default"). `override or default` would
    # incorrectly fall back to the default here; explicit `is not None`
    # selection must not.
    user = create_user(db_session, email="suspended@example.com", password="TestPassword123!")
    user.quota_monthly_analysis_seconds_override = 0
    user.quota_max_active_analysis_jobs_override = 0
    db_session.commit()

    token = login(client, email="suspended@example.com", password="TestPassword123!")
    response = client.get("/api/v1/quota/me", headers=auth_headers(token))
    body = response.json()
    assert body["monthly_analysis_seconds_limit"] == 0
    assert body["max_active_analysis_jobs"] == 0
    assert body["monthly_analysis_seconds_limit"] != test_settings.default_monthly_analysis_seconds
    assert body["max_active_analysis_jobs"] != test_settings.default_max_active_analysis_jobs

    project_id = client.post(
        "/api/v1/projects", json={"name": "Blocked"}, headers=auth_headers(token)
    ).json()["id"]
    initiate = client.post(
        f"/api/v1/projects/{project_id}/uploads",
        json={
            "filename": "match.mp4",
            "content_type": CONTENT_TYPE,
            "size_bytes": DECLARED_SIZE,
            "duration_seconds": DECLARED_DURATION,
            "part_count": 1,
        },
        headers=auth_headers(token),
    )
    assert initiate.status_code == 403, initiate.text
