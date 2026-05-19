import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user, get_storage
from app.models.project import Project, ProjectStatus
from app.models.user import User
from app.storage.base import StorageBackend

router = APIRouter(prefix="/api/projects/{project_id}/export", tags=["export"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def trigger_export(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    from app.tasks.export import export_highlights

    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == user.id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.status != ProjectStatus.READY:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project not ready for export")

    export_key = storage.generate_upload_key(str(user.id), "highlights.mp4")
    task = export_highlights.delay(str(project.id), f"/tmp/videos/{project.video_key}", export_key)
    project.celery_task_id = task.id
    project.status = ProjectStatus.EXPORTING
    await db.commit()

    return {"task_id": task.id, "status": "exporting"}


@router.get("/download")
async def get_download_url(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == user.id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    export_key = f"exports/{project.id}/highlights.mp4"
    url = await storage.generate_presigned_download_url(export_key)
    return {"download_url": url}
