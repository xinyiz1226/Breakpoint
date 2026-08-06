from __future__ import annotations

from fastapi.testclient import TestClient


def test_live_returns_ok(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ok_when_dependencies_are_healthy(client: TestClient) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["storage"] == "ok"


def test_ready_returns_503_when_storage_is_unavailable(client: TestClient, fake_storage) -> None:
    fake_storage.connection_ok = False
    response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["storage"] == "unavailable"
    assert body["checks"]["database"] == "ok"
