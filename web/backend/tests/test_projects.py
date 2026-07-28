from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import auth_headers, create_user, login


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
