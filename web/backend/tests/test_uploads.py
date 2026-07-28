from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.storage import ObjectMetadata
from tests.conftest import auth_headers, create_user, login
from tests.fakes import FakeObjectStorage

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
