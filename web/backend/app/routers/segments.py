import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models.project import Project, Segment
from app.models.user import User
from app.schemas.segment import SegmentResponse, SegmentListResponse, SegmentUpdate, SegmentBatchSelect

router = APIRouter(prefix="/api/projects/{project_id}/segments", tags=["segments"])


async def _get_user_project(project_id: uuid.UUID, user: User, db: AsyncSession) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == user.id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.get("", response_model=SegmentListResponse)
async def list_segments(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_project(project_id, user, db)
    result = await db.execute(
        select(Segment).where(Segment.project_id == project_id).order_by(Segment.index)
    )
    segments = result.scalars().all()
    return SegmentListResponse(segments=[SegmentResponse.model_validate(s) for s in segments])


@router.put("/{segment_id}", response_model=SegmentResponse)
async def update_segment(
    project_id: uuid.UUID,
    segment_id: uuid.UUID,
    body: SegmentUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_project(project_id, user, db)
    result = await db.execute(select(Segment).where(Segment.id == segment_id, Segment.project_id == project_id))
    segment = result.scalar_one_or_none()
    if segment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found")
    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(segment, key, value)
    await db.commit()
    await db.refresh(segment)
    return segment


@router.patch("/select")
async def batch_select(
    project_id: uuid.UUID,
    body: SegmentBatchSelect,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_project(project_id, user, db)
    result = await db.execute(
        update(Segment)
        .where(Segment.project_id == project_id, Segment.id.in_(body.segment_ids))
        .values(included=body.included)
    )
    await db.commit()
    return {"updated": result.rowcount}
