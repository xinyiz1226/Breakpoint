import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user, get_storage
from app.models.project import Project, ProjectStatus
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectCreateResponse, ProjectResponse, ProjectListResponse
from app.storage.base import StorageBackend

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("", response_model=ProjectCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    video_key = storage.generate_upload_key(str(user.id), body.video_filename)
    upload_url = await storage.generate_presigned_upload_url(video_key)

    project = Project(
        user_id=user.id,
        name=body.name,
        video_key=video_key,
        video_filename=body.video_filename,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    return ProjectCreateResponse(
        id=project.id,
        name=project.name,
        upload_url=upload_url,
        video_key=video_key,
    )


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(Project.user_id == user.id).order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    return ProjectListResponse(projects=[ProjectResponse.model_validate(p) for p in projects])


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == user.id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
):
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == user.id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.video_key:
        try:
            await storage.delete(project.video_key)
        except Exception:
            pass
    await db.delete(project)
    await db.commit()


@router.post("/{project_id}/analyze", status_code=status.HTTP_202_ACCEPTED)
async def trigger_analysis(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.tasks.analysis import analyze_video

    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == user.id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if project.status == ProjectStatus.ANALYZING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Analysis already in progress")

    task = analyze_video.delay(str(project.id), f"/tmp/videos/{project.video_key}")
    project.celery_task_id = task.id
    project.status = ProjectStatus.ANALYZING
    await db.commit()

    return {"task_id": task.id, "status": "analyzing"}


@router.get("/{project_id}/status")
async def get_status(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == user.id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return {"status": project.status, "error_message": project.error_message, "task_id": project.celery_task_id}
