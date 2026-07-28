from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cleanup import StorageCleanupTask
from app.models.enums import StorageCleanupOperation, StorageCleanupStatus, VideoAssetStatus
from app.models.job import AnalysisJob
from app.models.project import Project
from app.models.quota import QuotaLedgerEntry
from app.models.video import VideoAsset
from app.services.storage import ObjectMetadata
from tests.conftest import auth_headers, create_user, login
from tests.fakes import FakeObjectStorage

_CONTENT_TYPE = "video/mp4"
_DECLARED_SIZE = 10 * 1024 * 1024
_DECLARED_DURATION = 600.0


def _initiate_upload(client: TestClient, token: str, project_id: str):
    return client.post(
        f"/api/v1/projects/{project_id}/uploads",
        json={
            "filename": "match.mp4",
            "content_type": _CONTENT_TYPE,
            "size_bytes": _DECLARED_SIZE,
            "duration_seconds": _DECLARED_DURATION,
            "part_count": 1,
        },
        headers=auth_headers(token),
    )


def _finalize_upload(client: TestClient, token: str, project_id: str, video_asset_id: str):
    return client.post(
        f"/api/v1/projects/{project_id}/uploads/{video_asset_id}/finalize",
        json={"idempotency_key": "idem-1", "parts": [{"part_number": 1, "etag": "etag-1"}]},
        headers=auth_headers(token),
    )


def test_create_and_list_project(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="owner@example.com", password="password123")
    token = login(client, email="owner@example.com", password="password123")

    create_response = client.post(
        "/api/v1/projects", json={"name": "My Match"}, headers=auth_headers(token)
    )
    assert create_response.status_code == 201, create_response.text
    project_id = create_response.json()["id"]
    assert create_response.json()["has_video"] is False

    list_response = client.get("/api/v1/projects", headers=auth_headers(token))
    assert list_response.status_code == 200
    assert [p["id"] for p in list_response.json()] == [project_id]


def test_get_project_not_found(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="owner@example.com", password="password123")
    token = login(client, email="owner@example.com", password="password123")

    response = client.get(
        "/api/v1/projects/00000000-0000-0000-0000-000000000000", headers=auth_headers(token)
    )
    assert response.status_code == 404


def test_owner_cannot_access_other_users_project(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="owner@example.com", password="password123")
    create_user(db_session, email="intruder@example.com", password="password123")
    owner_token = login(client, email="owner@example.com", password="password123")
    intruder_token = login(client, email="intruder@example.com", password="password123")

    create_response = client.post(
        "/api/v1/projects", json={"name": "Private Match"}, headers=auth_headers(owner_token)
    )
    project_id = create_response.json()["id"]

    get_response = client.get(
        f"/api/v1/projects/{project_id}", headers=auth_headers(intruder_token)
    )
    assert get_response.status_code == 404

    update_response = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": "Stolen"},
        headers=auth_headers(intruder_token),
    )
    assert update_response.status_code == 404

    delete_response = client.delete(
        f"/api/v1/projects/{project_id}", headers=auth_headers(intruder_token)
    )
    assert delete_response.status_code == 404

    # The project is untouched from the true owner's perspective.
    owner_get_response = client.get(
        f"/api/v1/projects/{project_id}", headers=auth_headers(owner_token)
    )
    assert owner_get_response.status_code == 200


def test_owner_can_delete_own_project(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="owner@example.com", password="password123")
    token = login(client, email="owner@example.com", password="password123")

    create_response = client.post(
        "/api/v1/projects", json={"name": "Deletable"}, headers=auth_headers(token)
    )
    project_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers(token))
    assert delete_response.status_code == 204

    get_response = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers(token))
    assert get_response.status_code == 404


def test_owner_can_update_own_project(client: TestClient, db_session: Session) -> None:
    password = "valid-test-password"
    create_user(db_session, email="owner@example.com", password=password)
    token = login(client, email="owner@example.com", password=password)
    create_response = client.post(
        "/api/v1/projects", json={"name": "Before"}, headers=auth_headers(token)
    )
    project_id = create_response.json()["id"]

    update_response = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": "After"},
        headers=auth_headers(token),
    )

    assert update_response.status_code == 200
    assert update_response.json()["name"] == "After"


# --- Item 5: soft project deletion / tombstone ----------------------------------


def test_delete_project_tombstones_instead_of_hard_deleting(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="owner@example.com", password="valid-test-password")
    token = login(client, email="owner@example.com", password="valid-test-password")
    project_id = client.post(
        "/api/v1/projects", json={"name": "Deletable"}, headers=auth_headers(token)
    ).json()["id"]

    response = client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers(token))
    assert response.status_code == 204

    # The row is tombstoned, not gone: it still exists with deleted_at set.
    row = db_session.execute(
        select(Project).where(Project.id == uuid.UUID(project_id))
    ).scalar_one()
    assert row.deleted_at is not None


def test_deleted_project_excluded_from_list_get_patch_and_upload(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="owner@example.com", password="valid-test-password")
    token = login(client, email="owner@example.com", password="valid-test-password")
    project_id = client.post(
        "/api/v1/projects", json={"name": "Deletable"}, headers=auth_headers(token)
    ).json()["id"]

    delete_response = client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers(token))
    assert delete_response.status_code == 204

    assert client.get(f"/api/v1/projects/{project_id}", headers=auth_headers(token)).status_code == 404
    assert (
        client.patch(
            f"/api/v1/projects/{project_id}", json={"name": "x"}, headers=auth_headers(token)
        ).status_code
        == 404
    )
    assert project_id not in [
        p["id"] for p in client.get("/api/v1/projects", headers=auth_headers(token)).json()
    ]
    assert _initiate_upload(client, token, project_id).status_code == 404
    assert (
        client.get(
            f"/api/v1/projects/{project_id}/video/signed-url", headers=auth_headers(token)
        ).status_code
        == 404
    )
    # A second delete of an already-tombstoned project is also 404, not a
    # repeat tombstone/cleanup.
    assert client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers(token)).status_code == 404


def test_delete_project_with_initiated_upload_aborts_multipart_and_releases_reservations(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="owner@example.com", password="valid-test-password")
    token = login(client, email="owner@example.com", password="valid-test-password")
    project_id = client.post(
        "/api/v1/projects", json={"name": "Uploading"}, headers=auth_headers(token)
    ).json()["id"]
    initiate_body = _initiate_upload(client, token, project_id).json()
    video_asset_id = uuid.UUID(initiate_body["video_asset_id"])

    quota_before = client.get("/api/v1/quota/me", headers=auth_headers(token)).json()
    assert quota_before["storage_bytes_used"] == _DECLARED_SIZE
    assert quota_before["monthly_analysis_seconds_used"] == _DECLARED_DURATION

    response = client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers(token))
    assert response.status_code == 204

    # Reservations released.
    quota_after = client.get("/api/v1/quota/me", headers=auth_headers(token)).json()
    assert quota_after["storage_bytes_used"] == 0
    assert quota_after["monthly_analysis_seconds_used"] == 0

    # Child row survives (not hard-cascaded away). Durable cleanup was
    # queued for the never-completed multipart upload and, in this
    # synchronous best-effort path, completed -- reaching the same terminal
    # state a directly-aborted upload would.
    video_asset = db_session.get(VideoAsset, video_asset_id)
    assert video_asset is not None
    assert video_asset.status == VideoAssetStatus.UPLOAD_ABORTED

    task = (
        db_session.execute(
            select(StorageCleanupTask).where(StorageCleanupTask.video_asset_id == video_asset_id)
        )
        .scalars()
        .one()
    )
    assert task.operation == StorageCleanupOperation.ABORT_MULTIPART
    assert task.upload_id == initiate_body["upload_id"]
    assert task.status == StorageCleanupStatus.COMPLETED

    ledger_entries = (
        db_session.execute(
            select(QuotaLedgerEntry).where(QuotaLedgerEntry.video_asset_id == video_asset_id)
        )
        .scalars()
        .all()
    )
    assert len(ledger_entries) >= 2  # reservation + release, preserved for audit


def test_delete_project_with_uploaded_video_queues_delete_object_and_releases_once(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    create_user(db_session, email="owner@example.com", password="valid-test-password")
    token = login(client, email="owner@example.com", password="valid-test-password")
    project_id = client.post(
        "/api/v1/projects", json={"name": "Uploaded"}, headers=auth_headers(token)
    ).json()["id"]
    initiate_body = _initiate_upload(client, token, project_id).json()
    object_key = initiate_body["object_key"]
    fake_storage.objects[object_key] = ObjectMetadata(
        size_bytes=_DECLARED_SIZE, content_type=_CONTENT_TYPE
    )
    finalize_response = _finalize_upload(client, token, project_id, initiate_body["video_asset_id"])
    assert finalize_response.status_code == 200, finalize_response.text
    job_id = uuid.UUID(finalize_response.json()["analysis_job"]["id"])
    video_asset_id = uuid.UUID(initiate_body["video_asset_id"])

    response = client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers(token))
    assert response.status_code == 204

    # Object cleanup was queued (and, in this synchronous best-effort path,
    # completed) exactly once.
    assert fake_storage.deleted_object_keys.count(object_key) == 1
    assert object_key not in fake_storage.objects

    tasks = (
        db_session.execute(
            select(StorageCleanupTask).where(StorageCleanupTask.video_asset_id == video_asset_id)
        )
        .scalars()
        .all()
    )
    # Two tasks now exist for this asset: the multipart-expiry ABORT_MULTIPART
    # task scheduled at initiate time (cancelled once finalize durably
    # claimed this upload, so the expiry sweep can never abort a completed
    # request) and the DELETE_OBJECT task this project delete queued.
    delete_tasks = [t for t in tasks if t.operation == StorageCleanupOperation.DELETE_OBJECT]
    abort_tasks = [t for t in tasks if t.operation == StorageCleanupOperation.ABORT_MULTIPART]
    assert len(delete_tasks) == 1
    assert delete_tasks[0].status == StorageCleanupStatus.COMPLETED
    assert len(abort_tasks) == 1
    assert abort_tasks[0].status == StorageCleanupStatus.CANCELLED

    # Storage bytes released; counted bytes were released rather than
    # left permanently accounted against the user.
    quota_after = client.get("/api/v1/quota/me", headers=auth_headers(token)).json()
    assert quota_after["storage_bytes_used"] == 0

    # The job and video asset rows -- and their ledger history -- survive
    # the tombstone rather than being cascaded away.
    assert db_session.get(AnalysisJob, job_id) is not None
    assert db_session.get(VideoAsset, video_asset_id) is not None


def test_delete_project_with_active_job_frees_active_job_quota_for_new_upload(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    """A deleted project's still-QUEUED analysis job must not go on blocking
    every future upload against the user's active-job quota forever."""
    create_user(db_session, email="owner@example.com", password="valid-test-password")
    token = login(client, email="owner@example.com", password="valid-test-password")
    project_id = client.post(
        "/api/v1/projects", json={"name": "First"}, headers=auth_headers(token)
    ).json()["id"]
    initiate_body = _initiate_upload(client, token, project_id).json()
    object_key = initiate_body["object_key"]
    fake_storage.objects[object_key] = ObjectMetadata(
        size_bytes=_DECLARED_SIZE, content_type=_CONTENT_TYPE
    )
    finalize_response = _finalize_upload(client, token, project_id, initiate_body["video_asset_id"])
    assert finalize_response.status_code == 200, finalize_response.text
    job_id = uuid.UUID(finalize_response.json()["analysis_job"]["id"])

    second_project_id = client.post(
        "/api/v1/projects", json={"name": "Second"}, headers=auth_headers(token)
    ).json()["id"]
    # Under the test default max_active_analysis_jobs=1, a second upload is
    # blocked while the first project's job is still active.
    blocked = _initiate_upload(client, token, second_project_id)
    assert blocked.status_code == 403

    delete_response = client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers(token))
    assert delete_response.status_code == 204

    job = db_session.get(AnalysisJob, job_id)
    assert job.status == "cancelled"
    assert job.finished_at is not None
    assert job.failure_summary is not None

    allowed = _initiate_upload(client, token, second_project_id)
    assert allowed.status_code == 201, allowed.text


def test_admin_can_still_list_tombstoned_project(client: TestClient, db_session: Session) -> None:
    from app.models.enums import UserRole

    create_user(db_session, email="owner@example.com", password="valid-test-password")
    owner_token = login(client, email="owner@example.com", password="valid-test-password")
    project_id = client.post(
        "/api/v1/projects", json={"name": "Tombstoned"}, headers=auth_headers(owner_token)
    ).json()["id"]
    client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers(owner_token))

    create_user(db_session, email="admin@example.com", password="valid-test-password", role=UserRole.ADMIN)
    admin_token = login(client, email="admin@example.com", password="valid-test-password")

    response = client.get("/api/v1/admin/projects", headers=auth_headers(admin_token))
    assert response.status_code == 200
    matching = [p for p in response.json() if p["id"] == project_id]
    assert len(matching) == 1
    assert matching[0]["deleted_at"] is not None
