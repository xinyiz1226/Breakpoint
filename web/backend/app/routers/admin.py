"""Read-only admin APIs: users, projects, jobs, and failure summaries.

Every route here requires the admin role via ``require_admin`` and none of
them mutate, retry, or cancel anything -- that is intentionally out of scope
for this layer.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.models.enums import JobStatus
from app.models.job import AnalysisJob, ExportJob
from app.models.project import Project
from app.models.user import User
from app.schemas.admin import (
    AdminAnalysisJobRead,
    AdminExportJobRead,
    AdminProjectRead,
    AdminUserRead,
    FailureSummaryRead,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


@router.get("/users", response_model=list[AdminUserRead])
def list_users(
    db: Session = Depends(get_db),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> list[AdminUserRead]:
    users = (
        db.execute(select(User).order_by(User.created_at.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return [AdminUserRead.model_validate(user) for user in users]


@router.get("/projects", response_model=list[AdminProjectRead])
def list_projects(
    db: Session = Depends(get_db),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> list[AdminProjectRead]:
    projects = (
        db.execute(select(Project).order_by(Project.created_at.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return [AdminProjectRead.model_validate(project) for project in projects]


@router.get("/analysis-jobs", response_model=list[AdminAnalysisJobRead])
def list_analysis_jobs(
    db: Session = Depends(get_db),
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> list[AdminAnalysisJobRead]:
    stmt = select(AnalysisJob).order_by(AnalysisJob.created_at.desc())
    if status_filter is not None:
        stmt = stmt.where(AnalysisJob.status == status_filter)
    jobs = db.execute(stmt.limit(limit).offset(offset)).scalars().all()
    return [AdminAnalysisJobRead.model_validate(job) for job in jobs]


@router.get("/export-jobs", response_model=list[AdminExportJobRead])
def list_export_jobs(
    db: Session = Depends(get_db),
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> list[AdminExportJobRead]:
    stmt = select(ExportJob).order_by(ExportJob.created_at.desc())
    if status_filter is not None:
        stmt = stmt.where(ExportJob.status == status_filter)
    jobs = db.execute(stmt.limit(limit).offset(offset)).scalars().all()
    return [AdminExportJobRead.model_validate(job) for job in jobs]


@router.get("/failures", response_model=list[FailureSummaryRead])
def list_failures(
    db: Session = Depends(get_db),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> list[FailureSummaryRead]:
    failed_analysis_jobs = (
        db.execute(
            select(AnalysisJob)
            .where(AnalysisJob.status == JobStatus.FAILED)
            .order_by(AnalysisJob.finished_at.desc())
        )
        .scalars()
        .all()
    )
    failed_export_jobs = (
        db.execute(
            select(ExportJob)
            .where(ExportJob.status == JobStatus.FAILED)
            .order_by(ExportJob.finished_at.desc())
        )
        .scalars()
        .all()
    )

    summaries = [
        FailureSummaryRead(
            job_id=job.id,
            job_type="analysis",
            project_id=job.project_id,
            owner_id=job.owner_id,
            status=job.status,
            failure_summary=job.failure_summary,
            failure_detail=job.failure_detail,
            finished_at=job.finished_at,
        )
        for job in failed_analysis_jobs
    ] + [
        FailureSummaryRead(
            job_id=job.id,
            job_type="export",
            project_id=job.project_id,
            owner_id=job.owner_id,
            status=job.status,
            failure_summary=job.failure_summary,
            failure_detail=job.failure_detail,
            finished_at=job.finished_at,
        )
        for job in failed_export_jobs
    ]
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    summaries.sort(key=lambda summary: summary.finished_at or epoch, reverse=True)
    return summaries[offset : offset + limit]
