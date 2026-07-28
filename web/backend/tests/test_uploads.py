from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import get_db
from app.deps import get_email_sender, get_storage
from app.main import app
from app.models.cleanup import StorageCleanupTask
from app.models.enums import StorageCleanupOperation, StorageCleanupStatus, VideoAssetStatus
from app.models.job import AnalysisJob
from app.models.user import User
from app.models.video import VideoAsset
from app.services.storage import ObjectMetadata
from tests.conftest import auth_headers, create_user, login
from tests.fakes import FakeEmailSender, FakeObjectStorage

CONTENT_TYPE = "video/mp4"
DECLARED_SIZE = 10 * 1024 * 1024
DECLARED_DURATION = 600.0  # 10 minutes


def _create_project(client: TestClient, token: str, name: str = "Match") -> str:
    response = client.post("/api/v1/projects", json={"name": name}, headers=auth_headers(token))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _initiate_upload(
    client: TestClient,
    token: str,
    project_id: str,
    *,
    size_bytes: int = DECLARED_SIZE,
    duration_seconds: float = DECLARED_DURATION,
):
    return client.post(
        f"/api/v1/projects/{project_id}/uploads",
        json={
            "filename": "match.mp4",
            "content_type": CONTENT_TYPE,
            "size_bytes": size_bytes,
            "duration_seconds": duration_seconds,
            "part_count": 2,
        },
        headers=auth_headers(token),
    )


def _finalize_upload(
    client: TestClient,
    token: str,
    project_id: str,
    video_asset_id: str,
    *,
    idempotency_key: str = "idem-key-1",
    part_etags: tuple[str, str] = ("etag-1", "etag-2"),
):
    return client.post(
        f"/api/v1/projects/{project_id}/uploads/{video_asset_id}/finalize",
        json={
            "idempotency_key": idempotency_key,
            "parts": [
                {"part_number": 1, "etag": part_etags[0]},
                {"part_number": 2, "etag": part_etags[1]},
            ],
        },
        headers=auth_headers(token),
    )


def _finalize_upload_with_parts(
    client: TestClient,
    token: str,
    project_id: str,
    video_asset_id: str,
    *,
    parts: list[dict],
    idempotency_key: str = "idem-key-1",
):
    return client.post(
        f"/api/v1/projects/{project_id}/uploads/{video_asset_id}/finalize",
        json={"idempotency_key": idempotency_key, "parts": parts},
        headers=auth_headers(token),
    )


def _authenticated_project(client: TestClient, db_session: Session, email: str = "owner@example.com"):
    create_user(db_session, email=email, password="password123")
    token = login(client, email=email, password="password123")
    project_id = _create_project(client, token)
    return token, project_id


def test_initiate_upload_rejects_unsupported_content_type(
    client: TestClient, db_session: Session
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    response = client.post(
        f"/api/v1/projects/{project_id}/uploads",
        json={
            "filename": "match.exe",
            "content_type": "application/octet-stream",
            "size_bytes": 1024,
            "duration_seconds": DECLARED_DURATION,
            "part_count": 1,
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 415


def test_initiate_upload_rejects_oversized_declared_size(
    client: TestClient, db_session: Session, test_settings
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    response = _initiate_upload(
        client, token, project_id, size_bytes=test_settings.max_upload_size_bytes + 1
    )
    assert response.status_code == 413


def test_initiate_upload_rejects_declared_duration_over_cap(
    client: TestClient, db_session: Session, test_settings
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    response = _initiate_upload(
        client, token, project_id, duration_seconds=test_settings.max_video_duration_seconds + 1
    )
    assert response.status_code == 422, response.text


def test_initiate_upload_reserves_quota_and_blocks_when_exceeded(
    client: TestClient, db_session: Session, test_settings
) -> None:
    token, project_id = _authenticated_project(client, db_session)

    quota_response = client.get("/api/v1/quota/me", headers=auth_headers(token))
    assert quota_response.json()["monthly_analysis_seconds_used"] == 0

    first = _initiate_upload(client, token, project_id, duration_seconds=DECLARED_DURATION)
    assert first.status_code == 201, first.text

    quota_response = client.get("/api/v1/quota/me", headers=auth_headers(token))
    assert quota_response.json()["monthly_analysis_seconds_used"] == DECLARED_DURATION

    # Fill the rest of the monthly budget with more reservations, each
    # individually within the per-video duration cap but collectively
    # approaching the monthly limit.
    monthly_limit = test_settings.default_monthly_analysis_seconds
    per_video_cap = test_settings.max_video_duration_seconds
    reserved = DECLARED_DURATION
    while monthly_limit - reserved > per_video_cap:
        chunk_project_id = _create_project(client, token, name=f"Chunk {reserved}")
        chunk = min(per_video_cap, monthly_limit - reserved)
        response = _initiate_upload(client, token, chunk_project_id, duration_seconds=chunk)
        assert response.status_code == 201, response.text
        reserved += chunk

    # The next declared duration would push the reserved total over the
    # monthly limit and is rejected before any reservation is made, even
    # though every prior video's real duration is still unknown.
    remaining = monthly_limit - reserved
    over_project_id = _create_project(client, token, name="Over budget")
    over_budget = _initiate_upload(client, token, over_project_id, duration_seconds=remaining + 1)
    assert over_budget.status_code == 403, over_budget.text

    quota_response = client.get("/api/v1/quota/me", headers=auth_headers(token))
    assert quota_response.json()["monthly_analysis_seconds_used"] == reserved


def test_finalize_size_mismatch_releases_the_quota_reservation(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    fake_storage.objects[initiate_body["object_key"]] = ObjectMetadata(
        size_bytes=DECLARED_SIZE + 1, content_type=CONTENT_TYPE
    )

    quota_before = client.get("/api/v1/quota/me", headers=auth_headers(token)).json()
    assert quota_before["monthly_analysis_seconds_used"] == DECLARED_DURATION

    response = _finalize_upload(client, token, project_id, initiate_body["video_asset_id"])
    assert response.status_code == 422

    quota_after = client.get("/api/v1/quota/me", headers=auth_headers(token)).json()
    assert quota_after["monthly_analysis_seconds_used"] == 0


def test_initiate_and_finalize_upload_creates_queued_analysis_job(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    token, project_id = _authenticated_project(client, db_session)

    initiate_response = _initiate_upload(client, token, project_id)
    assert initiate_response.status_code == 201, initiate_response.text
    initiate_body = initiate_response.json()
    assert len(initiate_body["part_urls"]) == 2
    video_asset_id = initiate_body["video_asset_id"]
    object_key = initiate_body["object_key"]

    fake_storage.objects[object_key] = ObjectMetadata(
        size_bytes=DECLARED_SIZE, content_type=CONTENT_TYPE
    )

    finalize_response = _finalize_upload(client, token, project_id, video_asset_id)
    assert finalize_response.status_code == 200, finalize_response.text
    body = finalize_response.json()
    assert body["video_asset"]["status"] == "uploaded"
    assert body["video_asset"]["actual_size_bytes"] == DECLARED_SIZE
    assert body["video_asset"]["declared_duration_seconds"] == DECLARED_DURATION
    # Duration is worker-authoritative: this layer never probes media, so
    # both fields stay unset through initiate/finalize.
    assert body["video_asset"]["duration_seconds"] is None
    assert body["video_asset"]["duration_status"] is None
    assert body["analysis_job"]["status"] == "queued"


def test_finalize_is_idempotent_with_same_key_and_payload(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    video_asset_id = initiate_body["video_asset_id"]
    fake_storage.objects[initiate_body["object_key"]] = ObjectMetadata(
        size_bytes=DECLARED_SIZE, content_type=CONTENT_TYPE
    )

    first = _finalize_upload(client, token, project_id, video_asset_id)
    assert first.status_code == 200
    second = _finalize_upload(client, token, project_id, video_asset_id)
    assert second.status_code == 200
    assert first.json()["analysis_job"]["id"] == second.json()["analysis_job"]["id"]


def test_finalize_conflicts_with_same_key_but_different_payload(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    video_asset_id = initiate_body["video_asset_id"]
    fake_storage.objects[initiate_body["object_key"]] = ObjectMetadata(
        size_bytes=DECLARED_SIZE, content_type=CONTENT_TYPE
    )

    first = _finalize_upload(client, token, project_id, video_asset_id)
    assert first.status_code == 200

    conflicting = _finalize_upload(
        client, token, project_id, video_asset_id, part_etags=("different-etag", "etag-2")
    )
    assert conflicting.status_code == 409


def test_finalize_rejects_size_mismatch(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    video_asset_id = initiate_body["video_asset_id"]
    fake_storage.objects[initiate_body["object_key"]] = ObjectMetadata(
        size_bytes=DECLARED_SIZE + 1, content_type=CONTENT_TYPE
    )

    response = _finalize_upload(client, token, project_id, video_asset_id)
    assert response.status_code == 422


def test_finalize_rejects_content_type_mismatch_and_releases_reservation(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    video_asset_id = initiate_body["video_asset_id"]
    # Simulate the completed object actually having a different content
    # type than what was declared and accepted at initiate time.
    fake_storage.objects[initiate_body["object_key"]] = ObjectMetadata(
        size_bytes=DECLARED_SIZE, content_type="video/webm"
    )

    response = _finalize_upload(client, token, project_id, video_asset_id)
    assert response.status_code == 422, response.text

    quota_after = client.get("/api/v1/quota/me", headers=auth_headers(token)).json()
    assert quota_after["monthly_analysis_seconds_used"] == 0


def test_finalize_rejects_wrong_part_count_before_completing_storage(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    video_asset_id = initiate_body["video_asset_id"]
    upload_id = initiate_body["upload_id"]
    fake_storage.objects[initiate_body["object_key"]] = ObjectMetadata(
        size_bytes=DECLARED_SIZE, content_type=CONTENT_TYPE
    )

    # Only one part supplied for a 2-part upload.
    response = _finalize_upload_with_parts(
        client, token, project_id, video_asset_id, parts=[{"part_number": 1, "etag": "etag-1"}]
    )
    assert response.status_code == 422, response.text
    # Rejected before ever touching storage.
    assert upload_id not in fake_storage.completed_upload_ids


def test_finalize_rejects_duplicate_part_numbers_before_completing_storage(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    video_asset_id = initiate_body["video_asset_id"]
    upload_id = initiate_body["upload_id"]
    fake_storage.objects[initiate_body["object_key"]] = ObjectMetadata(
        size_bytes=DECLARED_SIZE, content_type=CONTENT_TYPE
    )

    # Part 1 supplied twice, part 2 never supplied.
    response = _finalize_upload_with_parts(
        client,
        token,
        project_id,
        video_asset_id,
        parts=[
            {"part_number": 1, "etag": "etag-1"},
            {"part_number": 1, "etag": "etag-1-again"},
        ],
    )
    assert response.status_code == 422, response.text
    assert upload_id not in fake_storage.completed_upload_ids


def test_second_video_upload_in_same_project_is_rejected(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    fake_storage.objects[initiate_body["object_key"]] = ObjectMetadata(
        size_bytes=DECLARED_SIZE, content_type=CONTENT_TYPE
    )
    _finalize_upload(client, token, project_id, initiate_body["video_asset_id"])

    second_initiate = _initiate_upload(client, token, project_id)
    assert second_initiate.status_code == 409


def test_upload_not_authorized_for_other_users_project(
    client: TestClient, db_session: Session
) -> None:
    _owner_token, project_id = _authenticated_project(client, db_session, email="owner@example.com")
    create_user(db_session, email="intruder@example.com", password="password123")
    intruder_token = login(client, email="intruder@example.com", password="password123")

    response = _initiate_upload(client, intruder_token, project_id)
    assert response.status_code == 404


def test_signed_url_requires_uploaded_video(client: TestClient, db_session: Session) -> None:
    token, project_id = _authenticated_project(client, db_session)
    response = client.get(
        f"/api/v1/projects/{project_id}/video/signed-url", headers=auth_headers(token)
    )
    assert response.status_code == 404


def test_signed_url_returns_url_after_finalize(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    fake_storage.objects[initiate_body["object_key"]] = ObjectMetadata(
        size_bytes=DECLARED_SIZE, content_type=CONTENT_TYPE
    )
    _finalize_upload(client, token, project_id, initiate_body["video_asset_id"])

    response = client.get(
        f"/api/v1/projects/{project_id}/video/signed-url", headers=auth_headers(token)
    )
    assert response.status_code == 200
    assert response.json()["url"].startswith("https://fake-s3.test/")


def test_signed_url_not_authorized_for_other_users_project(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    owner_token, project_id = _authenticated_project(client, db_session, email="owner@example.com")
    initiate_body = _initiate_upload(client, owner_token, project_id).json()
    fake_storage.objects[initiate_body["object_key"]] = ObjectMetadata(
        size_bytes=DECLARED_SIZE, content_type=CONTENT_TYPE
    )
    _finalize_upload(client, owner_token, project_id, initiate_body["video_asset_id"])

    create_user(db_session, email="intruder@example.com", password="password123")
    intruder_token = login(client, email="intruder@example.com", password="password123")
    response = client.get(
        f"/api/v1/projects/{project_id}/video/signed-url", headers=auth_headers(intruder_token)
    )
    assert response.status_code == 404


# --- Item 9: storage-byte quota -------------------------------------------------


def test_quota_me_exposes_storage_bytes_fields(
    client: TestClient, db_session: Session, test_settings: Settings
) -> None:
    create_user(db_session, email="owner@example.com", password="valid-test-password")
    token = login(client, email="owner@example.com", password="valid-test-password")

    response = client.get("/api/v1/quota/me", headers=auth_headers(token))
    body = response.json()
    assert body["storage_bytes_limit"] == test_settings.default_storage_bytes
    assert body["storage_bytes_used"] == 0
    assert body["storage_bytes_remaining"] == test_settings.default_storage_bytes


def test_initiate_upload_reserves_storage_bytes(
    client: TestClient, db_session: Session
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    quota_before = client.get("/api/v1/quota/me", headers=auth_headers(token)).json()
    assert quota_before["storage_bytes_used"] == 0

    _initiate_upload(client, token, project_id)

    quota_after = client.get("/api/v1/quota/me", headers=auth_headers(token)).json()
    assert quota_after["storage_bytes_used"] == DECLARED_SIZE


def test_initiate_upload_blocked_when_storage_quota_exceeded(
    client: TestClient, db_session: Session
) -> None:
    user = create_user(db_session, email="owner@example.com", password="valid-test-password")
    user.quota_storage_bytes_override = DECLARED_SIZE  # exactly one video's worth
    db_session.commit()
    token = login(client, email="owner@example.com", password="valid-test-password")
    project_id = _create_project(client, token)

    first = _initiate_upload(client, token, project_id, size_bytes=DECLARED_SIZE)
    assert first.status_code == 201, first.text

    over_project_id = _create_project(client, token, name="Over budget")
    over_budget = _initiate_upload(client, token, over_project_id, size_bytes=1)
    assert over_budget.status_code == 403, over_budget.text


def test_zero_storage_override_blocks_all_uploads(client: TestClient, db_session: Session) -> None:
    user = create_user(db_session, email="owner@example.com", password="valid-test-password")
    user.quota_storage_bytes_override = 0
    db_session.commit()
    token = login(client, email="owner@example.com", password="valid-test-password")
    project_id = _create_project(client, token)

    response = _initiate_upload(client, token, project_id)
    assert response.status_code == 403, response.text


def test_finalize_reconciles_reservation_to_counted_storage_bytes(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    fake_storage.objects[initiate_body["object_key"]] = ObjectMetadata(
        size_bytes=DECLARED_SIZE, content_type=CONTENT_TYPE
    )

    quota_before = client.get("/api/v1/quota/me", headers=auth_headers(token)).json()
    assert quota_before["storage_bytes_used"] == DECLARED_SIZE

    response = _finalize_upload(client, token, project_id, initiate_body["video_asset_id"])
    assert response.status_code == 200, response.text

    # Reservation was released and replaced by the counted actual size, not
    # double-counted alongside it.
    quota_after = client.get("/api/v1/quota/me", headers=auth_headers(token)).json()
    assert quota_after["storage_bytes_used"] == DECLARED_SIZE


def test_finalize_mismatch_releases_storage_reservation(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    fake_storage.objects[initiate_body["object_key"]] = ObjectMetadata(
        size_bytes=DECLARED_SIZE + 1, content_type=CONTENT_TYPE
    )

    response = _finalize_upload(client, token, project_id, initiate_body["video_asset_id"])
    assert response.status_code == 422

    quota_after = client.get("/api/v1/quota/me", headers=auth_headers(token)).json()
    assert quota_after["storage_bytes_used"] == 0


# --- Item 4: durable storage cleanup on finalize mismatch -----------------------


def test_finalize_mismatch_deletes_object_and_marks_cleanup_task_completed(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    object_key = initiate_body["object_key"]
    fake_storage.objects[object_key] = ObjectMetadata(
        size_bytes=DECLARED_SIZE + 1, content_type=CONTENT_TYPE
    )

    response = _finalize_upload(client, token, project_id, initiate_body["video_asset_id"])
    assert response.status_code == 422

    # The object that was actually completed by complete_multipart_upload
    # (even though it failed our own integrity check) must not be left
    # behind indefinitely: it's deleted, and the durable task recording
    # that is marked completed.
    assert object_key in fake_storage.deleted_object_keys
    assert object_key not in fake_storage.objects

    task = (
        db_session.query(StorageCleanupTask)
        .filter(
            StorageCleanupTask.object_key == object_key,
            StorageCleanupTask.operation == StorageCleanupOperation.DELETE_OBJECT,
        )
        .one()
    )
    assert task.operation == StorageCleanupOperation.DELETE_OBJECT
    assert task.status == StorageCleanupStatus.COMPLETED

    video_asset = db_session.get(VideoAsset, uuid.UUID(initiate_body["video_asset_id"]))
    assert video_asset.status == "upload_aborted"


def test_finalize_mismatch_with_injected_delete_failure_preserves_retryable_task(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    object_key = initiate_body["object_key"]
    fake_storage.objects[object_key] = ObjectMetadata(
        size_bytes=DECLARED_SIZE + 1, content_type=CONTENT_TYPE
    )
    fake_storage.fail_next_deletes = 1

    response = _finalize_upload(client, token, project_id, initiate_body["video_asset_id"])
    # The validation error is still returned even though cleanup failed.
    assert response.status_code == 422

    # The object was never actually deleted, but a durable, retryable task
    # records that it still needs to be -- no untracked/orphaned object.
    assert object_key in fake_storage.objects
    task = (
        db_session.query(StorageCleanupTask)
        .filter(
            StorageCleanupTask.object_key == object_key,
            StorageCleanupTask.operation == StorageCleanupOperation.DELETE_OBJECT,
        )
        .one()
    )
    assert task.status == StorageCleanupStatus.FAILED
    assert task.last_error is not None

    quota_after = client.get("/api/v1/quota/me", headers=auth_headers(token)).json()
    assert quota_after["storage_bytes_used"] == 0
    assert quota_after["monthly_analysis_seconds_used"] == 0


# --- Item 7: multipart initiation concurrency -----------------------------------


class _RacingObjectStorage(FakeObjectStorage):
    """A controllable fake that simulates a second, concurrent
    ``initiate_upload`` request committing its own ``VideoAsset`` for the
    same project in the window between this request's own
    "project has no video yet" check and its own persistence -- exercising
    the narrow ``IntegrityError`` recovery path without needing real
    threads (SQLite's ``.with_for_update()`` cannot simulate true lock
    contention).
    """

    def __init__(self, session_factory: sessionmaker, project_id, owner_id) -> None:
        super().__init__()
        self._session_factory = session_factory
        self._project_id = project_id
        self._owner_id = owner_id
        self._raced = False

    def create_multipart_upload(self, *, object_key: str, content_type: str) -> str:
        upload_id = super().create_multipart_upload(object_key=object_key, content_type=content_type)
        if not self._raced:
            self._raced = True
            session = self._session_factory()
            try:
                session.add(
                    VideoAsset(
                        project_id=self._project_id,
                        owner_id=self._owner_id,
                        object_key="projects/racer/source/winner.mp4",
                        original_filename="winner.mp4",
                        content_type=CONTENT_TYPE,
                        declared_size_bytes=DECLARED_SIZE,
                        declared_duration_seconds=DECLARED_DURATION,
                        upload_id="racing-upload-id",
                        part_count=1,
                    )
                )
                session.commit()
            finally:
                session.close()
        return upload_id


def test_losing_concurrent_initiate_request_aborts_its_multipart_and_leaves_no_orphan(
    session_factory: sessionmaker,
    test_settings: Settings,
    fake_email_sender: FakeEmailSender,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="owner@example.com", password="valid-test-password")

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    project_id = None
    racing_storage = None
    try:
        app.dependency_overrides[get_db] = override_get_db
        from app.config import get_settings as _get_settings

        app.dependency_overrides[_get_settings] = lambda: test_settings
        app.dependency_overrides[get_email_sender] = lambda: fake_email_sender

        with TestClient(app) as client:
            token = login(client, email="owner@example.com", password="valid-test-password")
            project_id = _create_project(client, token)

            racing_storage = _RacingObjectStorage(session_factory, uuid.UUID(project_id), owner.id)
            app.dependency_overrides[get_storage] = lambda: racing_storage

            response = _initiate_upload(client, token, project_id)
            assert response.status_code == 409, response.text
    finally:
        app.dependency_overrides.clear()

    assert racing_storage is not None
    # The losing request's own (real, storage-side) multipart upload was
    # aborted rather than left dangling.
    assert len(racing_storage.aborted_upload_ids) == 1

    session = session_factory()
    try:
        video_asset = (
            session.query(VideoAsset).filter(VideoAsset.project_id == uuid.UUID(project_id)).one()
        )
        # Exactly one asset survives -- the "winning" concurrent request's.
        assert video_asset.upload_id == "racing-upload-id"
    finally:
        session.close()


# --- Item 8: crash-safe finalize ------------------------------------------------


class _ClaimCheckingObjectStorage(FakeObjectStorage):
    """A controllable fake whose ``complete_multipart_upload`` verifies --
    via its own independent DB session -- that the caller already committed
    a durable ``FINALIZING`` claim (idempotency key + request fingerprint)
    *before* ever invoking this storage call, exercising the crash-safe
    finalize ordering directly rather than merely trusting it.
    """

    def __init__(self, session_factory: sessionmaker, video_asset_id: uuid.UUID) -> None:
        super().__init__()
        self._session_factory = session_factory
        self._video_asset_id = video_asset_id
        self.observed_claim: tuple[str, str | None, str | None] | None = None

    def complete_multipart_upload(self, *, object_key: str, upload_id: str, parts) -> None:
        session = self._session_factory()
        try:
            video_asset = session.get(VideoAsset, self._video_asset_id)
            self.observed_claim = (
                video_asset.status,
                video_asset.finalize_idempotency_key,
                video_asset.finalize_request_fingerprint,
            )
        finally:
            session.close()
        super().complete_multipart_upload(object_key=object_key, upload_id=upload_id, parts=parts)


def test_finalize_persists_finalizing_claim_before_calling_storage(
    client: TestClient, db_session: Session, session_factory: sessionmaker
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    video_asset_id = uuid.UUID(initiate_body["video_asset_id"])

    claim_checking_storage = _ClaimCheckingObjectStorage(session_factory, video_asset_id)
    from app.deps import get_storage as _get_storage

    app.dependency_overrides[_get_storage] = lambda: claim_checking_storage
    try:
        claim_checking_storage.objects[initiate_body["object_key"]] = ObjectMetadata(
            size_bytes=DECLARED_SIZE, content_type=CONTENT_TYPE
        )
        response = _finalize_upload(client, token, project_id, str(video_asset_id))
    finally:
        app.dependency_overrides.pop(_get_storage, None)

    assert response.status_code == 200, response.text
    assert claim_checking_storage.observed_claim is not None
    observed_status, observed_key, observed_fingerprint = claim_checking_storage.observed_claim
    assert observed_status == "finalizing"
    assert observed_key == "idem-key-1"
    assert observed_fingerprint is not None


def test_finalize_replay_after_ambiguous_completion_recovers_via_head_object(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    """Simulates a crash after S3 accepted CompleteMultipartUpload but before
    the process's own success handling ran: a replay with the same key and
    part payload must recover by verifying the object via head_object,
    rather than the storage layer silently treating NoSuchUpload as success.
    """
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    object_key = initiate_body["object_key"]

    # Simulate the earlier (crashed) attempt: the multipart upload was
    # already completed in storage, but our own process never got to
    # record success.
    fake_storage.completed_upload_ids.add(initiate_body["upload_id"])
    fake_storage.objects[object_key] = ObjectMetadata(
        size_bytes=DECLARED_SIZE, content_type=CONTENT_TYPE
    )

    response = _finalize_upload(client, token, project_id, initiate_body["video_asset_id"])
    assert response.status_code == 200, response.text
    assert response.json()["video_asset"]["status"] == "uploaded"

    # No duplicate job: replaying again returns the same one.
    replay = _finalize_upload(client, token, project_id, initiate_body["video_asset_id"])
    assert replay.status_code == 200, replay.text
    assert replay.json()["analysis_job"]["id"] == response.json()["analysis_job"]["id"]


# --- Item 4: genuine NoSuchUpload (no completed object exists) -----------------


def test_finalize_genuine_missing_upload_releases_reservations_and_aborts(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    """A NoSuchUpload that is *not* an ambiguous crashed-completion (the
    object never actually got completed in storage at all) must not be
    treated as recoverable: release reservations, mark the asset aborted,
    and return a non-retryable conflict -- never leave it stuck in
    FINALIZING.
    """
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    video_asset_id = uuid.UUID(initiate_body["video_asset_id"])

    # Simulate a genuinely unknown/expired multipart upload -- e.g. it was
    # never actually accepted, or expired -- rather than a crash after S3
    # accepted completion: complete_multipart_upload will raise
    # MultipartUploadNotFound, and since no object was ever completed,
    # head_object will then raise ObjectNotFound too -- the
    # genuinely-missing case, not the ambiguous one.
    del fake_storage.uploads[initiate_body["upload_id"]]
    response = _finalize_upload(client, token, project_id, initiate_body["video_asset_id"])
    assert response.status_code == 409, response.text

    video_asset = db_session.get(VideoAsset, video_asset_id)
    assert video_asset.status == "upload_aborted"
    assert video_asset.analysis_reserved_seconds == 0
    assert video_asset.storage_reserved_bytes == 0

    quota_after = client.get("/api/v1/quota/me", headers=auth_headers(token)).json()
    assert quota_after["storage_bytes_used"] == 0
    assert quota_after["monthly_analysis_seconds_used"] == 0

    job = db_session.execute(
        select(AnalysisJob).where(AnalysisJob.video_asset_id == video_asset_id)
    ).scalars().first()
    assert job is None


# --- Item 5: finalize/delete race -----------------------------------------------


class _TombstoningObjectStorage:
    """Wraps the test's existing storage fake -- so it retains knowledge of
    the multipart upload already created during initiate -- and tombstones
    the project via an independent DB session from inside
    ``complete_multipart_upload``, simulating a concurrent project delete
    that lands in the exact window between this finalize call's S3
    completion and its own re-lock.
    """

    def __init__(
        self, wrapped: FakeObjectStorage, session_factory: sessionmaker, project_id: uuid.UUID
    ) -> None:
        self._wrapped = wrapped
        self._session_factory = session_factory
        self._project_id = project_id

    def __getattr__(self, name: str):
        return getattr(self._wrapped, name)

    def complete_multipart_upload(self, *, object_key: str, upload_id: str, parts) -> None:
        self._wrapped.complete_multipart_upload(object_key=object_key, upload_id=upload_id, parts=parts)
        from app.models.base import utcnow
        from app.models.project import Project

        session = self._session_factory()
        try:
            project = session.get(Project, self._project_id)
            project.deleted_at = utcnow()
            session.commit()
        finally:
            session.close()


def test_finalize_returns_conflict_when_project_tombstoned_during_storage_completion(
    client: TestClient,
    db_session: Session,
    session_factory: sessionmaker,
    fake_storage: FakeObjectStorage,
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    video_asset_id = uuid.UUID(initiate_body["video_asset_id"])

    tombstoning_storage = _TombstoningObjectStorage(fake_storage, session_factory, uuid.UUID(project_id))
    from app.deps import get_storage as _get_storage

    app.dependency_overrides[_get_storage] = lambda: tombstoning_storage
    try:
        tombstoning_storage.objects[initiate_body["object_key"]] = ObjectMetadata(
            size_bytes=DECLARED_SIZE, content_type=CONTENT_TYPE
        )
        response = _finalize_upload(client, token, project_id, str(video_asset_id))
    finally:
        app.dependency_overrides.pop(_get_storage, None)

    assert response.status_code == 409, response.text

    session = session_factory()
    try:
        video_asset = session.get(VideoAsset, video_asset_id)
        assert video_asset.status != "uploaded"

        # No job was ever created for a tombstoned project.
        job = session.execute(
            select(AnalysisJob).where(AnalysisJob.video_asset_id == video_asset_id)
        ).scalars().first()
        assert job is None

        # A durable DELETE_OBJECT cleanup task exists for the object that
        # was, in fact, just completed in storage.
        task = session.execute(
            select(StorageCleanupTask).where(
                StorageCleanupTask.video_asset_id == video_asset_id,
                StorageCleanupTask.operation == StorageCleanupOperation.DELETE_OBJECT,
            )
        ).scalars().one()
        assert task.operation == StorageCleanupOperation.DELETE_OBJECT
    finally:
        session.close()

    # The object is gone (synchronous best-effort cleanup ran) and was
    # deleted exactly once -- no duplicate cleanup task/attempt.
    assert initiate_body["object_key"] not in tombstoning_storage.objects
    assert tombstoning_storage.deleted_object_keys.count(initiate_body["object_key"]) == 1


# --- Final review item 1: active-job-slot lost after object already exists ------


class _JobStealingObjectStorage:
    """Wraps the test's existing storage fake and, from inside
    ``complete_multipart_upload``, creates a competing ``AnalysisJob`` for
    the same owner via an independent DB session -- simulating a concurrent
    finalize elsewhere that fills the caller's last active-job slot in the
    exact window between this finalize call's S3 completion and its own
    re-lock. The point under test is that the object has, by then, already
    been completed in storage.
    """

    def __init__(self, wrapped: FakeObjectStorage, session_factory: sessionmaker, owner_id: uuid.UUID) -> None:
        self._wrapped = wrapped
        self._session_factory = session_factory
        self._owner_id = owner_id

    def __getattr__(self, name: str):
        return getattr(self._wrapped, name)

    def complete_multipart_upload(self, *, object_key: str, upload_id: str, parts) -> None:
        self._wrapped.complete_multipart_upload(object_key=object_key, upload_id=upload_id, parts=parts)
        from app.models.enums import JobStatus
        from app.models.project import Project

        session = self._session_factory()
        try:
            competing_project = Project(owner_id=self._owner_id, name="Competing")
            session.add(competing_project)
            session.flush()
            competing_asset = VideoAsset(
                project_id=competing_project.id,
                owner_id=self._owner_id,
                object_key="projects/competing/source/other.mp4",
                original_filename="other.mp4",
                content_type=CONTENT_TYPE,
                declared_size_bytes=1,
                declared_duration_seconds=1.0,
                status=VideoAssetStatus.UPLOADED,
                upload_id="upload-competing",
                part_count=1,
            )
            session.add(competing_asset)
            session.flush()
            competing_job = AnalysisJob(
                project_id=competing_project.id,
                video_asset_id=competing_asset.id,
                owner_id=self._owner_id,
                status=JobStatus.QUEUED,
            )
            session.add(competing_job)
            session.commit()
        finally:
            session.close()


def test_finalize_active_job_slot_lost_during_completion_queues_cleanup_and_returns_403(
    client: TestClient,
    db_session: Session,
    session_factory: sessionmaker,
    fake_storage: FakeObjectStorage,
) -> None:
    """If the caller's active-job slot fills up during the S3 completion
    call, the uploaded object already exists in storage by the time this
    is discovered -- so it must go through the same durable DELETE_OBJECT
    cleanup path as any other post-completion integrity failure, not the
    bare release-and-abort a pre-existing (never-completed) failure would
    use, which would leave the just-completed object orphaned.
    """
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    video_asset_id = uuid.UUID(initiate_body["video_asset_id"])

    owner_id = db_session.execute(
        select(User.id).where(User.email == "owner@example.com")
    ).scalar_one()

    stealing_storage = _JobStealingObjectStorage(fake_storage, session_factory, owner_id)
    app.dependency_overrides[get_storage] = lambda: stealing_storage
    try:
        stealing_storage.objects[initiate_body["object_key"]] = ObjectMetadata(
            size_bytes=DECLARED_SIZE, content_type=CONTENT_TYPE
        )
        response = _finalize_upload(client, token, project_id, str(video_asset_id))
    finally:
        app.dependency_overrides.pop(get_storage, None)

    assert response.status_code == 403, response.text

    session = session_factory()
    try:
        video_asset = session.get(VideoAsset, video_asset_id)
        assert video_asset.status == VideoAssetStatus.UPLOAD_ABORTED
        assert video_asset.analysis_reserved_seconds == 0
        assert video_asset.storage_reserved_bytes == 0

        task = session.execute(
            select(StorageCleanupTask).where(
                StorageCleanupTask.video_asset_id == video_asset_id,
                StorageCleanupTask.operation == StorageCleanupOperation.DELETE_OBJECT,
            )
        ).scalars().one()
        assert task.operation == StorageCleanupOperation.DELETE_OBJECT
        assert task.status == StorageCleanupStatus.COMPLETED
    finally:
        session.close()

    # The already-completed object was actually deleted -- no orphan left
    # behind just because the failure was discovered post-completion.
    assert initiate_body["object_key"] not in stealing_storage.objects
    assert initiate_body["object_key"] in stealing_storage.deleted_object_keys


# --- Final review item 2: no double-release on a concurrent tombstone race ------


class _ReservationClearingTombstoningObjectStorage:
    """Like ``_TombstoningObjectStorage``, but also performs the reservation
    release a real concurrent project delete would have already done for
    this asset before tombstoning the project -- so this finalize call's
    own post-S3 re-lock observes an already-fully-released asset, not just
    a tombstoned project.
    """

    def __init__(
        self,
        wrapped: FakeObjectStorage,
        session_factory: sessionmaker,
        project_id: uuid.UUID,
        video_asset_id: uuid.UUID,
    ) -> None:
        self._wrapped = wrapped
        self._session_factory = session_factory
        self._project_id = project_id
        self._video_asset_id = video_asset_id

    def __getattr__(self, name: str):
        return getattr(self._wrapped, name)

    def complete_multipart_upload(self, *, object_key: str, upload_id: str, parts) -> None:
        self._wrapped.complete_multipart_upload(object_key=object_key, upload_id=upload_id, parts=parts)
        from app.models.base import utcnow
        from app.models.project import Project
        from app.services import reservations as reservation_service

        session = self._session_factory()
        try:
            project = session.get(Project, self._project_id)
            video_asset = session.get(VideoAsset, self._video_asset_id)
            reservation_service.release_analysis_reservation(session, video_asset)
            reservation_service.release_storage_reservation(session, video_asset)
            project.deleted_at = utcnow()
            session.commit()
        finally:
            session.close()


def test_finalize_does_not_double_release_reservations_after_concurrent_tombstone(
    client: TestClient,
    db_session: Session,
    session_factory: sessionmaker,
    fake_storage: FakeObjectStorage,
) -> None:
    """A concurrent delete that already released this asset's reservations
    (as part of tombstoning the project) before this finalize call's own
    post-S3 re-lock must not be double-released here: the re-selected
    ``VideoAsset`` has to observe the already-zeroed durable fields, not a
    stale in-memory copy from before the concurrent commit -- otherwise
    quota usage goes negative.
    """
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    video_asset_id = uuid.UUID(initiate_body["video_asset_id"])

    concurrent_storage = _ReservationClearingTombstoningObjectStorage(
        fake_storage, session_factory, uuid.UUID(project_id), video_asset_id
    )
    app.dependency_overrides[get_storage] = lambda: concurrent_storage
    try:
        concurrent_storage.objects[initiate_body["object_key"]] = ObjectMetadata(
            size_bytes=DECLARED_SIZE, content_type=CONTENT_TYPE
        )
        response = _finalize_upload(client, token, project_id, str(video_asset_id))
    finally:
        app.dependency_overrides.pop(get_storage, None)

    assert response.status_code == 409, response.text

    quota_after = client.get("/api/v1/quota/me", headers=auth_headers(token)).json()
    assert quota_after["monthly_analysis_seconds_used"] == 0
    assert quota_after["storage_bytes_used"] == 0


# --- Rereview item 4: bounded multipart + expiry cleanup contract ---------------


def test_initiate_upload_exposes_content_length_bytes_summing_to_declared_size(
    client: TestClient, db_session: Session
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()

    part_urls = initiate_body["part_urls"]
    assert len(part_urls) == 2
    assert sum(part["content_length_bytes"] for part in part_urls) == DECLARED_SIZE
    # ceil(10 MiB / 2) = 5 MiB per part, evenly in this case.
    assert part_urls[0]["content_length_bytes"] == DECLARED_SIZE // 2
    assert part_urls[1]["content_length_bytes"] == DECLARED_SIZE // 2


def test_initiate_upload_allows_a_single_part_below_the_minimum_part_size(
    client: TestClient, db_session: Session, test_settings
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    tiny_size = min(1024, test_settings.multipart_min_part_size_bytes - 1)
    response = client.post(
        f"/api/v1/projects/{project_id}/uploads",
        json={
            "filename": "tiny.mp4",
            "content_type": CONTENT_TYPE,
            "size_bytes": tiny_size,
            "duration_seconds": DECLARED_DURATION,
            "part_count": 1,
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text
    part_urls = response.json()["part_urls"]
    assert len(part_urls) == 1
    assert part_urls[0]["content_length_bytes"] == tiny_size


def test_initiate_upload_rejects_a_non_final_part_smaller_than_the_minimum(
    client: TestClient, db_session: Session, test_settings, fake_storage: FakeObjectStorage
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    min_size = test_settings.multipart_min_part_size_bytes
    # part_count=2 with a declared size just under 2x the minimum makes the
    # non-final part smaller than the minimum (ceil((2*min - 100) / 2) ==
    # min - 50), which must be rejected before any multipart upload is
    # created in storage.
    undersized_total = 2 * min_size - 100
    response = client.post(
        f"/api/v1/projects/{project_id}/uploads",
        json={
            "filename": "undersized.mp4",
            "content_type": CONTENT_TYPE,
            "size_bytes": undersized_total,
            "duration_seconds": DECLARED_DURATION,
            "part_count": 2,
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 422, response.text
    assert len(fake_storage.uploads) == 0

    video_asset_count = (
        db_session.execute(select(VideoAsset).where(VideoAsset.project_id == uuid.UUID(project_id)))
        .scalars()
        .all()
    )
    assert video_asset_count == []


def test_initiate_upload_rejects_a_declared_size_too_small_for_the_part_count(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    """A declared size that cannot be split into ``part_count`` positive
    lengths (final part would be <= 0) must be rejected before creating a
    multipart upload -- a tiny declared size can never generate an
    unbounded/invalid number of parts."""
    token, project_id = _authenticated_project(client, db_session)
    response = client.post(
        f"/api/v1/projects/{project_id}/uploads",
        json={
            "filename": "toosmall.mp4",
            "content_type": CONTENT_TYPE,
            "size_bytes": 3,
            "duration_seconds": DECLARED_DURATION,
            "part_count": 5,
        },
        headers=auth_headers(token),
    )
    assert response.status_code == 422, response.text
    assert len(fake_storage.uploads) == 0


def test_initiate_upload_schedules_an_abort_multipart_expiry_cleanup_task(
    client: TestClient, db_session: Session, test_settings
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    video_asset_id = uuid.UUID(initiate_body["video_asset_id"])

    video_asset = db_session.get(VideoAsset, video_asset_id)
    assert video_asset.upload_expires_at is not None

    task = (
        db_session.execute(
            select(StorageCleanupTask).where(
                StorageCleanupTask.video_asset_id == video_asset_id,
                StorageCleanupTask.operation == StorageCleanupOperation.ABORT_MULTIPART,
            )
        )
        .scalars()
        .one()
    )
    assert task.status == StorageCleanupStatus.PENDING
    assert task.upload_id == initiate_body["upload_id"]
    assert task.not_before == video_asset.upload_expires_at


def test_finalize_cancels_the_scheduled_expiry_abort_task(
    client: TestClient, db_session: Session, fake_storage: FakeObjectStorage
) -> None:
    token, project_id = _authenticated_project(client, db_session)
    initiate_body = _initiate_upload(client, token, project_id).json()
    video_asset_id = uuid.UUID(initiate_body["video_asset_id"])
    fake_storage.objects[initiate_body["object_key"]] = ObjectMetadata(
        size_bytes=DECLARED_SIZE, content_type=CONTENT_TYPE
    )

    response = _finalize_upload(client, token, project_id, initiate_body["video_asset_id"])
    assert response.status_code == 200, response.text

    task = (
        db_session.execute(
            select(StorageCleanupTask).where(
                StorageCleanupTask.video_asset_id == video_asset_id,
                StorageCleanupTask.operation == StorageCleanupOperation.ABORT_MULTIPART,
            )
        )
        .scalars()
        .one()
    )
    assert task.status == StorageCleanupStatus.CANCELLED
