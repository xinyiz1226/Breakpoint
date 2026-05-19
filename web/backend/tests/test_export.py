import uuid
import pytest
from unittest.mock import patch, MagicMock

from app.models.user import User
from app.models.project import Project, ProjectStatus
from app.services.auth_service import hash_password, create_access_token


async def seed_ready_project(db):
    user = User(email=f"exp-{uuid.uuid4().hex[:6]}@example.com", hashed_password=hash_password("p"), display_name="T")
    db.add(user)
    await db.flush()
    project = Project(user_id=user.id, name="Match", video_key="k.mp4", video_filename="m.mp4", status=ProjectStatus.READY)
    db.add(project)
    await db.commit()
    for obj in [user, project]:
        await db.refresh(obj)
    headers = {"Authorization": f"Bearer {create_access_token(str(user.id))}"}
    return user, project, headers


@pytest.mark.asyncio
async def test_trigger_export(client, db):
    _, project, headers = await seed_ready_project(db)
    with patch("app.tasks.export.export_highlights.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="task-123")
        resp = await client.post(f"/api/projects/{project.id}/export", headers=headers)
    assert resp.status_code == 202
    assert resp.json()["task_id"] == "task-123"


@pytest.mark.asyncio
async def test_get_download_url(client, db):
    _, project, headers = await seed_ready_project(db)
    resp = await client.get(f"/api/projects/{project.id}/export/download", headers=headers)
    assert resp.status_code == 200
    assert "download_url" in resp.json()


@pytest.mark.asyncio
async def test_trigger_analysis(client, db):
    _, project, headers = await seed_ready_project(db)
    with patch("app.tasks.analysis.analyze_video.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="task-456")
        resp = await client.post(f"/api/projects/{project.id}/analyze", headers=headers)
    assert resp.status_code == 202
    assert resp.json()["task_id"] == "task-456"


@pytest.mark.asyncio
async def test_get_project_status(client, db):
    _, project, headers = await seed_ready_project(db)
    resp = await client.get(f"/api/projects/{project.id}/status", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
