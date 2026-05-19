import uuid
import pytest
from app.models.user import User
from app.models.project import Project, Segment, ProjectStatus
from app.services.auth_service import hash_password, create_access_token


async def seed_project_with_segments(db):
    user = User(email=f"seg-{uuid.uuid4().hex[:6]}@example.com", hashed_password=hash_password("p"), display_name="T")
    db.add(user)
    await db.flush()

    project = Project(user_id=user.id, name="Match", video_key="k", video_filename="m.mp4", status=ProjectStatus.READY)
    db.add(project)
    await db.flush()

    s1 = Segment(project_id=project.id, index=1, start=10.0, end=20.0, score=2.5, features={"hit_count": 5}, included=True)
    s2 = Segment(project_id=project.id, index=2, start=30.0, end=40.0, score=1.2, features={"hit_count": 3}, included=False)
    db.add_all([s1, s2])
    await db.commit()
    for obj in [user, project, s1, s2]:
        await db.refresh(obj)

    headers = {"Authorization": f"Bearer {create_access_token(str(user.id))}"}
    return user, project, [s1, s2], headers


@pytest.mark.asyncio
async def test_list_segments(client, db):
    _, project, _, headers = await seed_project_with_segments(db)
    resp = await client.get(f"/api/projects/{project.id}/segments", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["segments"]) == 2


@pytest.mark.asyncio
async def test_update_segment(client, db):
    _, project, segments, headers = await seed_project_with_segments(db)
    resp = await client.put(
        f"/api/projects/{project.id}/segments/{segments[0].id}",
        json={"start_adjusted": 11.0, "end_adjusted": 19.0, "included": False},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["start_adjusted"] == 11.0
    assert data["included"] is False


@pytest.mark.asyncio
async def test_batch_select(client, db):
    _, project, segments, headers = await seed_project_with_segments(db)
    resp = await client.patch(
        f"/api/projects/{project.id}/segments/select",
        json={"segment_ids": [str(segments[0].id), str(segments[1].id)], "included": True},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] == 2
