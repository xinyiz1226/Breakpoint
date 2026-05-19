import pytest
from app.models.user import User
from app.services.auth_service import hash_password, create_access_token


async def create_test_user(db, email="proj@example.com") -> tuple[User, dict]:
    user = User(email=email, hashed_password=hash_password("pass123"), display_name="Test")
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_access_token(str(user.id))
    return user, {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_project(client, db):
    user, headers = await create_test_user(db)
    resp = await client.post("/api/projects", json={"name": "Test Match", "video_filename": "match.mp4"}, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Match"
    assert "upload_url" in data
    assert "video_key" in data


@pytest.mark.asyncio
async def test_list_projects(client, db):
    user, headers = await create_test_user(db)
    await client.post("/api/projects", json={"name": "Match 1", "video_filename": "a.mp4"}, headers=headers)
    await client.post("/api/projects", json={"name": "Match 2", "video_filename": "b.mp4"}, headers=headers)
    resp = await client.get("/api/projects", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["projects"]) == 2


@pytest.mark.asyncio
async def test_get_project(client, db):
    user, headers = await create_test_user(db)
    create_resp = await client.post("/api/projects", json={"name": "Match", "video_filename": "m.mp4"}, headers=headers)
    project_id = create_resp.json()["id"]
    resp = await client.get(f"/api/projects/{project_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Match"


@pytest.mark.asyncio
async def test_delete_project(client, db):
    user, headers = await create_test_user(db)
    create_resp = await client.post("/api/projects", json={"name": "Del", "video_filename": "d.mp4"}, headers=headers)
    project_id = create_resp.json()["id"]
    resp = await client.delete(f"/api/projects/{project_id}", headers=headers)
    assert resp.status_code == 204
    resp = await client.get(f"/api/projects/{project_id}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_other_users_project(client, db):
    user1, headers1 = await create_test_user(db, email="owner@example.com")
    user2, headers2 = await create_test_user(db, email="other@example.com")

    create_resp = await client.post("/api/projects", json={"name": "Private", "video_filename": "p.mp4"}, headers=headers1)
    project_id = create_resp.json()["id"]
    resp = await client.get(f"/api/projects/{project_id}", headers=headers2)
    assert resp.status_code == 404
